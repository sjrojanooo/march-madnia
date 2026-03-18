"""Bracket visualization and export utilities.

Provides rich CLI displays of simulation results and export to CSV / JSON
for further analysis or submission.

Usage:
    from src.bracket.visualizer import (
        print_bracket,
        print_championship_odds,
        print_upset_alerts,
        export_csv,
        export_json,
    )

    print_bracket(results)
    export_csv(results, "predictions.csv")
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pandas as pd
from rich.console import Console
from rich.style import Style
from rich.table import Table
from rich.text import Text

from src.bracket.simulator import ROUND_NAMES, SimulationResults

logger = logging.getLogger(__name__)

console = Console()

# Confidence color thresholds.
_HIGH_CONFIDENCE = 0.75
_MED_CONFIDENCE = 0.50

_STYLE_HIGH = Style(color="green", bold=True)
_STYLE_MED = Style(color="yellow")
_STYLE_LOW = Style(color="red")


def _confidence_style(prob: float) -> Style:
    """Return a rich Style based on win-probability confidence."""
    if prob >= _HIGH_CONFIDENCE:
        return _STYLE_HIGH
    if prob >= _MED_CONFIDENCE:
        return _STYLE_MED
    return _STYLE_LOW


def _pct(prob: float) -> str:
    """Format a probability as a percentage string."""
    return f"{prob * 100:.1f}%"


# ---------------------------------------------------------------------------
# Bracket display
# ---------------------------------------------------------------------------


def print_bracket(results: SimulationResults) -> None:
    """Rich CLI bracket display with color-coded confidence levels.

    Shows each round's picks along with the predicted win probability.
    Games are grouped by round and sorted by game number.
    Colors: green (>75% confidence), yellow (50-75%), red (<50%).
    """
    console.print()
    console.rule("[bold blue]NCAA Tournament Bracket Predictions")
    console.print(f"[dim]Based on {results.n_simulations:,} Monte Carlo simulations[/dim]")
    console.print()

    # Group predictions by round.
    games_by_round: dict[str, list[dict]] = {}
    for gp in results.game_predictions:
        games_by_round.setdefault(gp["round"], []).append(gp)

    for round_name in ROUND_NAMES:
        games = games_by_round.get(round_name, [])
        if not games:
            continue

        table = Table(
            title=f"[bold]{round_name}[/bold]",
            show_header=True,
            header_style="bold cyan",
            border_style="dim",
            pad_edge=True,
        )
        table.add_column("#", justify="right", width=4)
        table.add_column("Matchup", min_width=35)
        table.add_column("Pick", min_width=20)
        table.add_column("Prob", justify="right", width=8)
        table.add_column("Upset?", justify="center", width=7)

        for gp in sorted(games, key=lambda g: g["game_number"]):
            matchup = f"({gp['seed_a']}) {gp['team_a']}  vs  ({gp['seed_b']}) {gp['team_b']}"
            prob = gp["win_probability"]
            style = _confidence_style(prob)

            pick_text = Text(gp["predicted_winner"])
            pick_text.stylize(style)

            prob_text = Text(_pct(prob))
            prob_text.stylize(style)

            upset_marker = "[bold red]!!![/bold red]" if gp["upset"] else ""

            table.add_row(
                str(gp["game_number"]),
                matchup,
                pick_text,
                prob_text,
                upset_marker,
            )

        console.print(table)
        console.print()


# ---------------------------------------------------------------------------
# Championship odds
# ---------------------------------------------------------------------------


def print_championship_odds(results: SimulationResults, top_n: int = 16) -> None:
    """Rich table showing top N teams by championship probability."""
    console.print()
    console.rule("[bold blue]Championship Odds")
    console.print(
        f"[dim]Top {top_n} teams by championship probability "
        f"({results.n_simulations:,} simulations)[/dim]"
    )
    console.print()

    sorted_teams = sorted(results.champion_probs.items(), key=lambda kv: kv[1], reverse=True)[
        :top_n
    ]

    table = Table(
        show_header=True,
        header_style="bold cyan",
        border_style="dim",
    )
    table.add_column("Rank", justify="right", width=5)
    table.add_column("Team", min_width=25)
    table.add_column("Champion", justify="right", width=10)
    table.add_column("Final Four", justify="right", width=11)
    table.add_column("Elite 8", justify="right", width=10)
    table.add_column("Sweet 16", justify="right", width=10)

    for rank, (team, champ_prob) in enumerate(sorted_teams, start=1):
        adv = results.advancement_probs.get(team, {})
        ff_prob = adv.get("Final Four", 0.0)
        e8_prob = adv.get("Elite 8", 0.0)
        s16_prob = adv.get("Sweet 16", 0.0)

        champ_style = _confidence_style(champ_prob)
        champ_text = Text(_pct(champ_prob))
        champ_text.stylize(champ_style)

        table.add_row(
            str(rank),
            team,
            champ_text,
            _pct(ff_prob),
            _pct(e8_prob),
            _pct(s16_prob),
        )

    console.print(table)
    console.print()


# ---------------------------------------------------------------------------
# Upset alerts
# ---------------------------------------------------------------------------


def print_upset_alerts(results: SimulationResults) -> None:
    """Rich table showing potential upsets."""
    console.print()
    console.rule("[bold red]Upset Alerts")
    console.print("[dim]Games where the lower seed wins >= 35% of simulations[/dim]")
    console.print()

    if not results.upset_alerts:
        console.print("[green]No major upset alerts detected.[/green]")
        console.print()
        return

    table = Table(
        show_header=True,
        header_style="bold red",
        border_style="dim",
    )
    table.add_column("Round", min_width=14)
    table.add_column("Favored", min_width=22)
    table.add_column("Seed", justify="center", width=5)
    table.add_column("Underdog", min_width=22)
    table.add_column("Seed", justify="center", width=5)
    table.add_column("Upset Prob", justify="right", width=11)

    for alert in results.upset_alerts:
        prob_text = Text(_pct(alert.upset_probability))
        if alert.upset_probability >= 0.50:
            prob_text.stylize("bold red")
        else:
            prob_text.stylize("yellow")

        table.add_row(
            alert.round_name,
            alert.higher_seed_team,
            str(alert.higher_seed),
            alert.lower_seed_team,
            str(alert.lower_seed),
            prob_text,
        )

    console.print(table)
    console.print()

    # Cinderella tracker
    if results.cinderella_tracker:
        console.rule("[bold magenta]Cinderella Tracker")
        console.print("[dim]Mid-major teams (seed >= 10) with best deep-run odds[/dim]")
        console.print()

        cin_table = Table(
            show_header=True,
            header_style="bold magenta",
            border_style="dim",
        )
        cin_table.add_column("Team", min_width=22)
        cin_table.add_column("Seed", justify="center", width=5)
        cin_table.add_column("Sweet 16", justify="right", width=10)
        cin_table.add_column("Elite 8", justify="right", width=10)
        cin_table.add_column("Final Four", justify="right", width=11)
        cin_table.add_column("Champion", justify="right", width=10)

        for cin in results.cinderella_tracker[:10]:
            cin_table.add_row(
                cin["team"],
                str(cin["seed"]),
                _pct(cin["sweet_16_prob"]),
                _pct(cin["elite_8_prob"]),
                _pct(cin["final_four_prob"]),
                _pct(cin["champion_prob"]),
            )

        console.print(cin_table)
        console.print()


# ---------------------------------------------------------------------------
# CSV export
# ---------------------------------------------------------------------------


def export_csv(results: SimulationResults, path: str) -> None:
    """Export all 63 game predictions to CSV.

    Columns: round, game_number, team_a, seed_a, team_b, seed_b,
    predicted_winner, win_probability, upset.
    """
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    df = pd.DataFrame(results.game_predictions)

    # Ensure column order.
    col_order = [
        "round",
        "game_number",
        "team_a",
        "seed_a",
        "team_b",
        "seed_b",
        "predicted_winner",
        "win_probability",
        "upset",
    ]
    cols = [c for c in col_order if c in df.columns]
    df = df[cols]

    df.to_csv(output_path, index=False)
    logger.info("Exported %d game predictions to %s", len(df), output_path)
    console.print(f"[green]CSV exported to {output_path}[/green]")


# ---------------------------------------------------------------------------
# JSON export
# ---------------------------------------------------------------------------


def export_json(results: SimulationResults, path: str) -> None:
    """Export full simulation results to JSON.

    Includes: bracket picks, advancement probabilities, upset alerts,
    champion probabilities, cinderella tracker, and all game predictions.
    """
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    data = {
        "metadata": {
            "n_simulations": results.n_simulations,
        },
        "best_bracket": results.best_bracket,
        "champion_probabilities": dict(
            sorted(
                results.champion_probs.items(),
                key=lambda kv: kv[1],
                reverse=True,
            )
        ),
        "final_four_probabilities": dict(
            sorted(
                results.final_four_probs.items(),
                key=lambda kv: kv[1],
                reverse=True,
            )
        ),
        "advancement_probabilities": results.advancement_probs,
        "upset_alerts": [
            {
                "round": alert.round_name,
                "favored_team": alert.higher_seed_team,
                "favored_seed": alert.higher_seed,
                "underdog_team": alert.lower_seed_team,
                "underdog_seed": alert.lower_seed,
                "upset_probability": alert.upset_probability,
            }
            for alert in results.upset_alerts
        ],
        "cinderella_tracker": results.cinderella_tracker,
        "game_predictions": results.game_predictions,
    }

    with open(output_path, "w") as f:
        json.dump(data, f, indent=2)

    logger.info("Exported full results to %s", output_path)
    console.print(f"[green]JSON exported to {output_path}[/green]")
