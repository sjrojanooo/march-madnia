"""Monte Carlo bracket simulator for NCAA March Madness predictions.

Runs thousands of tournament simulations using a trained sklearn model to
produce probabilistic bracket predictions, upset alerts, and advancement
probabilities for all 64 teams.

Usage:
    from src.bracket.simulator import BracketSimulator

    sim = BracketSimulator(model=pipeline, team_features=features_dict)
    results = sim.simulate(bracket)
    print(results.champion_probs)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import numpy as np
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn

from src.features.matchup import build_prediction_matchup

logger = logging.getLogger(__name__)

# Standard NCAA tournament seed matchups per region (first round pairings).
# Each tuple is (higher_seed, lower_seed).
FIRST_ROUND_MATCHUPS: list[tuple[int, int]] = [
    (1, 16),
    (8, 9),
    (5, 12),
    (4, 13),
    (6, 11),
    (3, 14),
    (7, 10),
    (2, 15),
]

# Second round matchups: winners of the above pairings play each other.
# Index pairs into FIRST_ROUND_MATCHUPS results.
SECOND_ROUND_PAIRS: list[tuple[int, int]] = [
    (0, 1),  # 1/16 winner vs 8/9 winner
    (2, 3),  # 5/12 winner vs 4/13 winner
    (4, 5),  # 6/11 winner vs 3/14 winner
    (6, 7),  # 7/10 winner vs 2/15 winner
]

# Sweet 16 matchups: pairs of second-round winners.
SWEET_16_PAIRS: list[tuple[int, int]] = [
    (0, 1),  # top half
    (2, 3),  # bottom half
]

# Elite 8: Sweet 16 winners play each other.
ELITE_8_PAIR: tuple[int, int] = (0, 1)

ROUND_NAMES: list[str] = [
    "Round of 64",
    "Round of 32",
    "Sweet 16",
    "Elite 8",
    "Final Four",
    "Championship",
]

# Mid-major threshold: seeds >= this are tracked as potential Cinderellas.
CINDERELLA_SEED_THRESHOLD = 10

# Upset alert threshold: lower seed wins this often or more.
UPSET_ALERT_THRESHOLD = 0.35


@dataclass
class UpsetAlert:
    """A game where the lower-seeded team wins frequently in simulations."""

    round_name: str
    higher_seed_team: str
    higher_seed: int
    lower_seed_team: str
    lower_seed: int
    upset_probability: float


@dataclass
class SimulationResults:
    """Aggregated results from Monte Carlo bracket simulations.

    Attributes:
        best_bracket: Dict mapping each game label to the most-likely winner.
        advancement_probs: {team: {round_name: probability}} for each team
            reaching each round.
        champion_probs: {team: probability} of winning the championship.
        final_four_probs: {team: probability} of reaching the Final Four.
        upset_alerts: Games where lower seed wins >= 35% of simulations.
        cinderella_tracker: Mid-major teams (seed >= 10) sorted by Sweet 16+
            probability.
        n_simulations: Number of simulations that were run.
        game_predictions: List of per-game prediction dicts for CSV/JSON export.
    """

    best_bracket: dict[str, str] = field(default_factory=dict)
    advancement_probs: dict[str, dict[str, float]] = field(default_factory=dict)
    champion_probs: dict[str, float] = field(default_factory=dict)
    final_four_probs: dict[str, float] = field(default_factory=dict)
    upset_alerts: list[UpsetAlert] = field(default_factory=list)
    cinderella_tracker: list[dict] = field(default_factory=list)
    n_simulations: int = 0
    game_predictions: list[dict] = field(default_factory=list)


class BracketSimulator:
    """Monte Carlo simulator for the NCAA tournament bracket.

    Parameters
    ----------
    model
        A trained sklearn model (or Pipeline) exposing ``predict_proba``.
        Must accept the same feature columns produced by
        ``build_prediction_matchup``.
    team_features : dict[str, dict]
        Pre-computed feature dictionaries keyed by team name.  Each value is
        a dict whose keys match ``RAW_FEATURE_COLS`` from
        ``src.features.matchup`` (e.g. ``adj_em``, ``seed``, ``tempo``, ...).
    n_simulations : int
        Number of Monte Carlo bracket simulations to run (default 10 000).
    seed : int
        Random seed for reproducibility.
    """

    def __init__(
        self,
        model,
        team_features: dict[str, dict],
        n_simulations: int = 10_000,
        seed: int = 42,
        feature_names: list[str] | None = None,
    ) -> None:
        self.model = model
        self.team_features = team_features
        self.n_simulations = n_simulations
        self.rng = np.random.default_rng(seed)
        self.feature_names = feature_names

        # Pre-compute and cache pairwise win probabilities to avoid
        # redundant model calls across simulations.
        self._prob_cache: dict[tuple[str, str], float] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def simulate(self, bracket: dict) -> SimulationResults:
        """Run the full Monte Carlo simulation over the tournament bracket.

        Parameters
        ----------
        bracket : dict
            Tournament structure::

                {
                    "regions": {
                        "South": {"1": "Duke", "16": "Norfolk St", ...},
                        "East":  {...},
                        "West":  {...},
                        "Midwest": {...},
                    },
                    "first_four": {          # optional
                        "team_in": "team_out",  # winner: loser
                    }
                }

            Each region maps seed strings ("1" .. "16") to team names.

        Returns
        -------
        SimulationResults
        """
        regions = bracket["regions"]
        region_names = list(regions.keys())

        if len(region_names) != 4:
            raise ValueError(f"Expected 4 regions, got {len(region_names)}: {region_names}")

        logger.info(
            "Starting %d Monte Carlo simulations across 4 regions",
            self.n_simulations,
        )

        # Pre-warm the probability cache for all possible first-round games.
        self._warm_cache(regions)

        # Track how many times each team reaches each round.
        # Keys: team name -> round_name -> count
        advancement_counts: dict[str, dict[str, int]] = {}
        champion_counts: dict[str, int] = {}
        final_four_counts: dict[str, int] = {}

        # Track per-game winner counts for best_bracket / game_predictions.
        # game_label -> {team: count}
        game_winner_counts: dict[str, dict[str, int]] = {}
        # game_label -> (team_a, seed_a, team_b, seed_b, round_name)
        game_metadata: dict[str, tuple[str, int, str, int, str]] = {}
        # game_label -> {(team_a, team_b, seed_a, seed_b): count} to track most common matchup
        game_matchup_counts: dict[str, dict[tuple[str, str, int, int], int]] = {}

        with Progress(
            SpinnerColumn(),
            TextColumn("[bold blue]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        ) as progress:
            task = progress.add_task("Simulating brackets...", total=self.n_simulations)

            for _ in range(self.n_simulations):
                sim_result = self._simulate_bracket_once(regions, region_names)

                # Accumulate advancement counts.
                for team, rounds_reached in sim_result["advancements"].items():
                    if team not in advancement_counts:
                        advancement_counts[team] = {r: 0 for r in ROUND_NAMES}
                    for round_name in rounds_reached:
                        advancement_counts[team][round_name] += 1

                # Accumulate champion.
                champ = sim_result["champion"]
                champion_counts[champ] = champion_counts.get(champ, 0) + 1

                # Accumulate Final Four.
                for ff_team in sim_result["final_four"]:
                    final_four_counts[ff_team] = final_four_counts.get(ff_team, 0) + 1

                # Accumulate per-game winners.
                for game_label, info in sim_result["games"].items():
                    if game_label not in game_winner_counts:
                        game_winner_counts[game_label] = {}
                        game_metadata[game_label] = (
                            info["team_a"],
                            info["seed_a"],
                            info["team_b"],
                            info["seed_b"],
                            info["round"],
                        )
                        game_matchup_counts[game_label] = {}
                    winner = info["winner"]
                    game_winner_counts[game_label][winner] = (
                        game_winner_counts[game_label].get(winner, 0) + 1
                    )
                    # Track matchup combinations
                    matchup_key = (
                        info["team_a"],
                        info["team_b"],
                        info["seed_a"],
                        info["seed_b"],
                    )
                    game_matchup_counts[game_label][matchup_key] = (
                        game_matchup_counts[game_label].get(matchup_key, 0) + 1
                    )

                progress.advance(task)

        # --- Aggregate results ------------------------------------------------
        n = self.n_simulations

        advancement_probs: dict[str, dict[str, float]] = {}
        for team, counts in advancement_counts.items():
            advancement_probs[team] = {r: c / n for r, c in counts.items()}

        champion_probs = {t: c / n for t, c in champion_counts.items()}
        final_four_probs = {t: c / n for t, c in final_four_counts.items()}

        # Best bracket: most-likely winner for each game.
        best_bracket: dict[str, str] = {}
        for game_label, winners in game_winner_counts.items():
            best_bracket[game_label] = max(winners, key=winners.get)

        # Game predictions for export.
        # For each game_label, find the most common matchup first, then the winner.
        game_predictions: list[dict] = []
        game_number = 0
        for game_label in sorted(
            game_metadata.keys(),
            key=lambda gl: (ROUND_NAMES.index(game_metadata[gl][4]), gl),
        ):
            round_name = game_metadata[game_label][4]

            # Find the most common matchup for this game_label
            matchup_counts = game_matchup_counts.get(game_label, {})
            if matchup_counts:
                most_common_matchup = max(matchup_counts, key=matchup_counts.get)
                team_a, team_b, seed_a, seed_b = most_common_matchup
            else:
                # Fallback to first observed matchup
                team_a, seed_a, team_b, seed_b, _ = game_metadata[game_label]

            winners = game_winner_counts[game_label]
            predicted_winner = max(winners, key=winners.get)
            win_prob = winners[predicted_winner] / n
            is_upset = (seed_a < seed_b and predicted_winner == team_b) or (
                seed_b < seed_a and predicted_winner == team_a
            )

            game_number += 1
            game_predictions.append(
                {
                    "round": round_name,
                    "game_number": game_number,
                    "game_label": game_label,
                    "team_a": team_a,
                    "seed_a": seed_a,
                    "team_b": team_b,
                    "seed_b": seed_b,
                    "predicted_winner": predicted_winner,
                    "win_probability": round(win_prob, 4),
                    "upset": is_upset,
                }
            )

        # Upset alerts.
        upset_alerts: list[UpsetAlert] = []
        for gp in game_predictions:
            team_a, seed_a = gp["team_a"], gp["seed_a"]
            team_b, seed_b = gp["team_b"], gp["seed_b"]
            if seed_a == seed_b:
                continue

            if seed_a < seed_b:
                higher_seed_team, higher_seed = team_a, seed_a
                lower_seed_team, lower_seed = team_b, seed_b
            else:
                higher_seed_team, higher_seed = team_b, seed_b
                lower_seed_team, lower_seed = team_a, seed_a

            game_label_key = gp["game_label"]
            lower_seed_wins = game_winner_counts[game_label_key].get(lower_seed_team, 0)
            upset_prob = lower_seed_wins / n

            if upset_prob >= UPSET_ALERT_THRESHOLD:
                upset_alerts.append(
                    UpsetAlert(
                        round_name=gp["round"],
                        higher_seed_team=higher_seed_team,
                        higher_seed=higher_seed,
                        lower_seed_team=lower_seed_team,
                        lower_seed=lower_seed,
                        upset_probability=round(upset_prob, 4),
                    )
                )

        upset_alerts.sort(key=lambda u: u.upset_probability, reverse=True)

        # Cinderella tracker.
        cinderella_tracker: list[dict] = []
        for team, feat in self.team_features.items():
            seed = int(feat.get("seed", 0))
            if seed >= CINDERELLA_SEED_THRESHOLD:
                probs = advancement_probs.get(team, {})
                sweet_16_prob = probs.get("Sweet 16", 0.0)
                elite_8_prob = probs.get("Elite 8", 0.0)
                final_four_prob = probs.get("Final Four", 0.0)
                best_round_prob = max(sweet_16_prob, elite_8_prob, final_four_prob)
                if best_round_prob > 0:
                    cinderella_tracker.append(
                        {
                            "team": team,
                            "seed": seed,
                            "sweet_16_prob": round(sweet_16_prob, 4),
                            "elite_8_prob": round(elite_8_prob, 4),
                            "final_four_prob": round(final_four_prob, 4),
                            "champion_prob": round(champion_probs.get(team, 0.0), 4),
                        }
                    )

        cinderella_tracker.sort(key=lambda c: c["sweet_16_prob"], reverse=True)

        logger.info(
            "Simulation complete. Top champion: %s (%.1f%%)",
            max(champion_probs, key=champion_probs.get) if champion_probs else "N/A",
            max(champion_probs.values(), default=0) * 100,
        )

        return SimulationResults(
            best_bracket=best_bracket,
            advancement_probs=advancement_probs,
            champion_probs=champion_probs,
            final_four_probs=final_four_probs,
            upset_alerts=upset_alerts,
            cinderella_tracker=cinderella_tracker,
            n_simulations=n,
            game_predictions=game_predictions,
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _predict_game(self, team_a: str, team_b: str) -> float:
        """Return P(team_a wins) using the trained model.

        Results are cached so each unique matchup only requires one model
        call across all simulations.
        """
        key = (team_a, team_b)
        if key in self._prob_cache:
            return self._prob_cache[key]

        # Check the reverse key (P(b beats a) = 1 - P(a beats b)).
        reverse_key = (team_b, team_a)
        if reverse_key in self._prob_cache:
            prob = 1.0 - self._prob_cache[reverse_key]
            self._prob_cache[key] = prob
            return prob

        feat_a = self.team_features.get(team_a)
        feat_b = self.team_features.get(team_b)

        if feat_a is None or feat_b is None:
            missing = []
            if feat_a is None:
                missing.append(team_a)
            if feat_b is None:
                missing.append(team_b)
            logger.warning(
                "Missing features for %s; defaulting to 0.5",
                ", ".join(missing),
            )
            self._prob_cache[key] = 0.5
            return 0.5

        matchup_df = build_prediction_matchup(feat_a, feat_b)

        # Filter to the feature columns the model was trained on
        if self.feature_names is not None:
            for col in self.feature_names:
                if col not in matchup_df.columns:
                    matchup_df[col] = 0.0
            matchup_df = matchup_df[self.feature_names]

        # Fill any remaining NaN
        matchup_df = matchup_df.fillna(0.0)

        prob_a = float(self.model.predict_proba(matchup_df.values)[0, 1])

        self._prob_cache[key] = prob_a
        self._prob_cache[reverse_key] = 1.0 - prob_a
        return prob_a

    def _warm_cache(self, regions: dict[str, dict[str, str]]) -> None:
        """Pre-compute win probabilities for all first-round matchups."""
        logger.info("Pre-computing pairwise win probabilities...")
        for _region_name, seeds_teams in regions.items():
            for higher_seed, lower_seed in FIRST_ROUND_MATCHUPS:
                team_a = seeds_teams.get(str(higher_seed))
                team_b = seeds_teams.get(str(lower_seed))
                if team_a and team_b:
                    self._predict_game(team_a, team_b)

    def _play_game(self, team_a: str, team_b: str) -> str:
        """Simulate a single game outcome using the model probability."""
        prob_a = self._predict_game(team_a, team_b)
        return team_a if self.rng.random() < prob_a else team_b

    def _simulate_region(
        self,
        seeds_teams: dict[str, str],
        region_name: str,
        advancements: dict[str, list[str]],
        games: dict[str, dict],
    ) -> str:
        """Simulate one region (4 rounds) and return the region winner.

        Side-effects: populates ``advancements`` and ``games`` dicts.
        """
        # --- Round of 64 -----------------------------------------------------
        r64_winners: list[tuple[str, int]] = []
        for higher_seed, lower_seed in FIRST_ROUND_MATCHUPS:
            team_a = seeds_teams[str(higher_seed)]
            team_b = seeds_teams[str(lower_seed)]

            winner = self._play_game(team_a, team_b)
            winner_seed = higher_seed if winner == team_a else lower_seed

            game_label = f"{region_name}_R64_{higher_seed}v{lower_seed}"
            games[game_label] = {
                "team_a": team_a,
                "seed_a": higher_seed,
                "team_b": team_b,
                "seed_b": lower_seed,
                "winner": winner,
                "round": "Round of 64",
            }

            # Both teams "reached" Round of 64 by being in the bracket.
            advancements.setdefault(team_a, []).append("Round of 64")
            advancements.setdefault(team_b, []).append("Round of 64")

            r64_winners.append((winner, winner_seed))

        # --- Round of 32 -----------------------------------------------------
        r32_winners: list[tuple[str, int]] = []
        for idx_a, idx_b in SECOND_ROUND_PAIRS:
            team_a, seed_a = r64_winners[idx_a]
            team_b, seed_b = r64_winners[idx_b]

            winner = self._play_game(team_a, team_b)
            winner_seed = seed_a if winner == team_a else seed_b

            game_label = f"{region_name}_R32_{seed_a}v{seed_b}"
            games[game_label] = {
                "team_a": team_a,
                "seed_a": seed_a,
                "team_b": team_b,
                "seed_b": seed_b,
                "winner": winner,
                "round": "Round of 32",
            }

            advancements[team_a].append("Round of 32")
            advancements[team_b].append("Round of 32")
            r32_winners.append((winner, winner_seed))

        # --- Sweet 16 --------------------------------------------------------
        s16_winners: list[tuple[str, int]] = []
        for idx_a, idx_b in SWEET_16_PAIRS:
            team_a, seed_a = r32_winners[idx_a]
            team_b, seed_b = r32_winners[idx_b]

            winner = self._play_game(team_a, team_b)
            winner_seed = seed_a if winner == team_a else seed_b

            game_label = f"{region_name}_S16_{seed_a}v{seed_b}"
            games[game_label] = {
                "team_a": team_a,
                "seed_a": seed_a,
                "team_b": team_b,
                "seed_b": seed_b,
                "winner": winner,
                "round": "Sweet 16",
            }

            advancements[team_a].append("Sweet 16")
            advancements[team_b].append("Sweet 16")
            s16_winners.append((winner, winner_seed))

        # --- Elite 8 ---------------------------------------------------------
        team_a, seed_a = s16_winners[ELITE_8_PAIR[0]]
        team_b, seed_b = s16_winners[ELITE_8_PAIR[1]]

        winner = self._play_game(team_a, team_b)
        winner_seed = seed_a if winner == team_a else seed_b

        game_label = f"{region_name}_E8_{seed_a}v{seed_b}"
        games[game_label] = {
            "team_a": team_a,
            "seed_a": seed_a,
            "team_b": team_b,
            "seed_b": seed_b,
            "winner": winner,
            "round": "Elite 8",
        }

        advancements[team_a].append("Elite 8")
        advancements[team_b].append("Elite 8")

        return winner

    def _simulate_bracket_once(
        self,
        regions: dict[str, dict[str, str]],
        region_names: list[str],
    ) -> dict:
        """Run one full bracket simulation.

        Returns a dict with keys:
            - ``advancements``: {team: [round_names reached]}
            - ``champion``: winning team name
            - ``final_four``: list of 4 Final Four teams
            - ``games``: {game_label: game_info_dict}
        """
        advancements: dict[str, list[str]] = {}
        games: dict[str, dict] = {}

        # Simulate each region.
        region_winners: list[tuple[str, int]] = []
        for rname in region_names:
            seeds_teams = regions[rname]
            winner = self._simulate_region(seeds_teams, rname, advancements, games)
            winner_seed = int(self.team_features.get(winner, {}).get("seed", 0))
            region_winners.append((winner, winner_seed))

        final_four_teams = [t for t, _ in region_winners]

        # --- Final Four (semi-finals) ----------------------------------------
        # Standard pairing: region 0 vs region 1, region 2 vs region 3.
        semi_a_team_a, semi_a_seed_a = region_winners[0]
        semi_a_team_b, semi_a_seed_b = region_winners[1]
        semi_a_winner = self._play_game(semi_a_team_a, semi_a_team_b)
        semi_a_winner_seed = semi_a_seed_a if semi_a_winner == semi_a_team_a else semi_a_seed_b

        games[f"FF_{region_names[0]}v{region_names[1]}"] = {
            "team_a": semi_a_team_a,
            "seed_a": semi_a_seed_a,
            "team_b": semi_a_team_b,
            "seed_b": semi_a_seed_b,
            "winner": semi_a_winner,
            "round": "Final Four",
        }
        advancements[semi_a_team_a].append("Final Four")
        advancements[semi_a_team_b].append("Final Four")

        semi_b_team_a, semi_b_seed_a = region_winners[2]
        semi_b_team_b, semi_b_seed_b = region_winners[3]
        semi_b_winner = self._play_game(semi_b_team_a, semi_b_team_b)
        semi_b_winner_seed = semi_b_seed_a if semi_b_winner == semi_b_team_a else semi_b_seed_b

        games[f"FF_{region_names[2]}v{region_names[3]}"] = {
            "team_a": semi_b_team_a,
            "seed_a": semi_b_seed_a,
            "team_b": semi_b_team_b,
            "seed_b": semi_b_seed_b,
            "winner": semi_b_winner,
            "round": "Final Four",
        }
        advancements[semi_b_team_a].append("Final Four")
        advancements[semi_b_team_b].append("Final Four")

        # --- Championship -----------------------------------------------------
        champion = self._play_game(semi_a_winner, semi_b_winner)

        games["Championship"] = {
            "team_a": semi_a_winner,
            "seed_a": semi_a_winner_seed,
            "team_b": semi_b_winner,
            "seed_b": semi_b_winner_seed,
            "winner": champion,
            "round": "Championship",
        }
        advancements[semi_a_winner].append("Championship")
        advancements[semi_b_winner].append("Championship")

        return {
            "advancements": advancements,
            "champion": champion,
            "final_four": final_four_teams,
            "games": games,
        }
