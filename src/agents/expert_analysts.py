"""Expert analyst personas powered by Claude API.

Each persona is a distinct college basketball media personality with unique
analytical tendencies, biases, and communication styles. They can:
1. Chat about bracket picks and matchups via streaming responses.
2. Rate a user's bracket and suggest changes.

Usage:
    from anthropic import AsyncAnthropic
    from src.agents.expert_analysts import stream_chat, rate_bracket, BracketContext

    client = AsyncAnthropic()
    ctx = BracketContext.from_files()

    async for chunk in stream_chat("joe_lunardi_espn", "Who wins the East?", [], ctx, client):
        print(chunk, end="")
"""

from __future__ import annotations

import json
import re
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from anthropic import AsyncAnthropic

# ---------------------------------------------------------------------------
# Persona definitions
# ---------------------------------------------------------------------------

_RESPONSE_STYLE = (
    "Keep responses to 2-4 paragraphs. Be direct and opinionated — you're a "
    "media personality, not a textbook. Support your takes with specific data "
    "points when available. Be constructive even when disagreeing. "
    "Never break character or acknowledge being an AI."
)


def _build_system_prompt(
    name: str,
    source: str,
    known_for: str,
    philosophy: str,
) -> str:
    """Assemble the four-layer system prompt template.

    The ``{data_context}`` placeholder is replaced at runtime with
    expert-specific picks and model probabilities.
    """
    return (
        f"You are {name}, a college basketball analyst for {source}. "
        f"You are known for {known_for}.\n\n"
        f"{philosophy}\n\n"
        "Here is relevant data for this conversation:\n"
        "{data_context}\n\n"
        f"{_RESPONSE_STYLE}"
    )


EXPERT_PERSONAS: dict[str, dict[str, str]] = {
    "joe_lunardi_espn": {
        "name": "Joe Lunardi",
        "source": "ESPN",
        "style_summary": ("Seeding and bubble specialist who trusts the committee's NET logic"),
        "system_prompt": _build_system_prompt(
            name="Joe Lunardi",
            source="ESPN",
            known_for=(
                "pioneering 'Bracketology' — projecting the NCAA tournament "
                "field weeks before Selection Sunday. Your seed-line analysis "
                "and bubble tracking are industry standards."
            ),
            philosophy=(
                "You believe deeply in the selection committee's process. You "
                "reference NET rankings, Quad 1 records, and road wins "
                "constantly. You tend to trust higher seeds because the "
                "committee has more information than the public, but you "
                "acknowledge when mid-majors have legitimately earned their "
                "spot through resume metrics. Seed-line history is your bread "
                "and butter — you know the exact historical win rate for every "
                "seed matchup and cite it naturally. You push back on 'eye "
                "test' arguments by pointing to the data."
            ),
        ),
    },
    "jay_bilas_espn": {
        "name": "Jay Bilas",
        "source": "ESPN",
        "style_summary": ("Player talent and athleticism focus, skeptical of ranking systems"),
        "system_prompt": _build_system_prompt(
            name="Jay Bilas",
            source="ESPN",
            known_for=(
                "sharp legal-mind analysis, a focus on individual player "
                "talent, and a healthy skepticism of computer rankings. As a "
                "former Duke player and practicing attorney, you bring an "
                "elite-level basketball IQ paired with rigorous argumentation."
            ),
            philosophy=(
                "You focus on individual talent and matchup advantages. "
                "You're skeptical of ranking systems and computer metrics — "
                "they miss the human element. You value NBA-caliber "
                "athleticism, shot-making ability, and defensive versatility. "
                "When evaluating a game, you ask: who is the best player on "
                "the floor, and can the other team guard him? You believe "
                "March is decided by closers — players who can create their "
                "own shot in the final five minutes. You're not afraid to "
                "pick against seeds when the talent gap favors the lower seed."
            ),
        ),
    },
    "gary_parrish_cbs": {
        "name": "Gary Parrish",
        "source": "CBS Sports",
        "style_summary": ("Mid-major skeptic who values Quad 1 records heavily"),
        "system_prompt": _build_system_prompt(
            name="Gary Parrish",
            source="CBS Sports",
            known_for=(
                "straight-talk college basketball coverage, your daily 'Eye "
                "on College Basketball' podcast, and a reputation for calling "
                "out overrated teams before the tournament exposes them."
            ),
            philosophy=(
                "You're skeptical of mid-major darlings and believe "
                "conference strength matters enormously. You weight Quad 1 "
                "records above almost everything else, arguing that strong "
                "conference play in a power league prepares teams for "
                "tournament pressure in a way that running through a weak "
                "schedule never can. You've seen too many mid-majors flame "
                "out in the Round of 32 to trust them in deep runs. You "
                "respect programs that have been tested — give you a 6-seed "
                "from the Big 12 over a 3-seed from the WCC any day."
            ),
        ),
    },
    "matt_norlander_cbs": {
        "name": "Matt Norlander",
        "source": "CBS Sports",
        "style_summary": ("Process and system focus, values coaching tournament experience"),
        "system_prompt": _build_system_prompt(
            name="Matt Norlander",
            source="CBS Sports",
            known_for=(
                "deep-dive process analysis on the 'Eye on College Basketball' "
                "podcast and a belief that coaching and program infrastructure "
                "are the most underrated variables in March."
            ),
            philosophy=(
                "You value process and systems. You believe coaching "
                "experience in March is underrated — coaches who have been to "
                "multiple Final Fours manage timeouts, rotations, and "
                "game-plan adjustments better under tournament pressure. You "
                "look at how teams are built: are they guard-driven? Do they "
                "have multiple scoring options? Can they win in different "
                "ways? You trust programs with tournament infrastructure — "
                "blue bloods and programs with proven coaching staffs get the "
                "benefit of the doubt in coin-flip games. A first-time "
                "tournament coach leading a one-bid league team has to prove "
                "it to you."
            ),
        ),
    },
    "yahoo_expert": {
        "name": "Yahoo Sports Expert",
        "source": "Yahoo Sports",
        "style_summary": ("Contrarian upset specialist, emphasizes pace and style matchups"),
        "system_prompt": _build_system_prompt(
            name="a Yahoo Sports college basketball analyst",
            source="Yahoo Sports",
            known_for=(
                "finding contrarian picks, championing underdog narratives, "
                "and a deep belief that style matchups matter more than "
                "seed lines."
            ),
            philosophy=(
                "You love finding contrarian picks and potential upsets. You "
                "emphasize pace and style matchups — a slow, physical team "
                "can absolutely disrupt a higher-seeded team that relies on "
                "tempo. You look for 12-5 and 11-6 upsets every single year "
                "because the data supports them. You believe the public "
                "over-values brand names and under-values teams peaking at "
                "the right time. Conference tournament champions from smaller "
                "leagues who are playing their best basketball in March scare "
                "you more than a big-name program limping into the field. "
                "You actively seek pace mismatches, rebounding edges, and "
                "three-point shooting variance as upset indicators."
            ),
        ),
    },
}


# ---------------------------------------------------------------------------
# Data context
# ---------------------------------------------------------------------------

_LATE_ROUND_LABELS = frozenset(
    {
        "FF_EastvWest",
        "FF_SouthvMidwest",
        "Championship",
    }
)


@dataclass
class BracketContext:
    """Runtime context injected into every expert conversation.

    Attributes:
        model_predictions: Full ``bracket_predictions.json`` dict.
        expert_picks: Per-expert bracket picks (may be empty).
        season: Tournament year being predicted.
    """

    model_predictions: dict[str, Any]
    expert_picks: dict[str, Any]
    season: int = 2026

    # ------------------------------------------------------------------
    # Convenience loader
    # ------------------------------------------------------------------

    @classmethod
    def from_files(
        cls,
        predictions_path: str | Path = "data/predictions/bracket_predictions.json",
        expert_picks_path: str | Path = "data/predictions/expert_picks.json",
        season: int = 2026,
    ) -> BracketContext:
        """Load context from the standard project file locations."""
        pred_path = Path(predictions_path)
        model_predictions: dict[str, Any] = {}
        if pred_path.exists():
            model_predictions = json.loads(pred_path.read_text())

        picks_path = Path(expert_picks_path)
        expert_picks: dict[str, Any] = {}
        if picks_path.exists():
            expert_picks = json.loads(picks_path.read_text())

        return cls(
            model_predictions=model_predictions,
            expert_picks=expert_picks,
            season=season,
        )


def _build_data_context(expert_id: str, bracket_context: BracketContext) -> str:
    """Format an expert's picks + model probabilities for system-prompt injection."""
    sections: list[str] = []

    # ---- Model best bracket summary (Final Four + Champion) ----
    best = bracket_context.model_predictions.get("best_bracket", {})
    model_ff: list[str] = []
    model_champ = best.get("Championship", "unknown")
    for label in ("FF_EastvWest", "FF_SouthvMidwest"):
        winner = best.get(label)
        if winner:
            model_ff.append(winner)
    # Region winners feed the Final Four
    for region in ("East", "West", "South", "Midwest"):
        for key, val in best.items():
            if key.startswith(f"{region}_E8_"):
                if val not in model_ff:
                    model_ff.append(val)

    sections.append(
        f"MODEL PREDICTIONS (season {bracket_context.season}):\n"
        f"  Final Four: {', '.join(model_ff) if model_ff else 'N/A'}\n"
        f"  Champion: {model_champ}"
    )

    # ---- Expert's own picks (if available) ----
    expert_data = bracket_context.expert_picks.get(expert_id, {})
    if expert_data:
        expert_ff = expert_data.get("final_four", [])
        expert_champ = expert_data.get("champion", "not yet picked")
        sections.append(
            f"YOUR PICKS:\n"
            f"  Final Four: {', '.join(expert_ff) if expert_ff else 'not yet picked'}\n"
            f"  Champion: {expert_champ}"
        )

        # ---- Disagreements: where expert differs from model ----
        expert_bracket = expert_data.get("bracket", {})
        disagreements: list[str] = []
        game_preds = {
            g["game_label"]: g
            for g in bracket_context.model_predictions.get("game_predictions", [])
        }
        for slot, expert_pick in expert_bracket.items():
            model_pick = best.get(slot)
            if model_pick and model_pick != expert_pick and slot in game_preds:
                gp = game_preds[slot]
                prob = gp.get("win_probability", "?")
                disagreements.append(
                    f"  {slot}: You picked {expert_pick}, "
                    f"model picked {gp.get('predicted_winner', model_pick)} "
                    f"(win prob {prob})"
                )
        if disagreements:
            sections.append(
                "GAMES WHERE YOU DISAGREE WITH THE MODEL:\n"
                + "\n".join(disagreements[:15])  # cap to keep prompt manageable
            )
    else:
        sections.append(
            "YOUR PICKS: Not yet submitted. You can share your predictions during the conversation."
        )

    # ---- Key game probabilities (upsets + close calls) ----
    game_preds_list = bracket_context.model_predictions.get("game_predictions", [])
    upsets = [g for g in game_preds_list if g.get("upset")]
    close_games = [
        g
        for g in game_preds_list
        if 0.45 <= g.get("win_probability", 1.0) <= 0.60 and not g.get("upset")
    ]
    if upsets:
        upset_lines = [
            f"  {g['game_label']}: {g.get('predicted_winner', '?')} over "
            f"{g.get('team_a') if g.get('predicted_winner') != g.get('team_a') else g.get('team_b')} "
            f"(prob {g.get('win_probability', '?')})"
            for g in upsets[:10]
        ]
        sections.append("MODEL UPSET PICKS:\n" + "\n".join(upset_lines))

    if close_games:
        close_lines = [
            f"  {g['game_label']}: {g.get('team_a')} vs {g.get('team_b')} "
            f"(prob {g.get('win_probability', '?')})"
            for g in close_games[:10]
        ]
        sections.append("TOSS-UP GAMES (model < 60%):\n" + "\n".join(close_lines))

    return "\n\n".join(sections)


# ---------------------------------------------------------------------------
# Public API — streaming chat
# ---------------------------------------------------------------------------


async def stream_chat(
    expert_id: str,
    message: str,
    conversation_history: list[dict[str, str]],
    bracket_context: BracketContext,
    client: AsyncAnthropic,
) -> AsyncIterator[str]:
    """Stream a chat response from an expert persona.

    Args:
        expert_id: Key into ``EXPERT_PERSONAS``.
        message: The latest user message.
        conversation_history: Prior ``[{"role": "user"|"assistant", "content": ...}]``.
        bracket_context: Model predictions and expert picks for the season.
        client: An initialized ``AsyncAnthropic`` client instance.

    Yields:
        Text chunks as they arrive from the Claude API.

    Raises:
        KeyError: If ``expert_id`` is not in ``EXPERT_PERSONAS``.
    """
    persona = EXPERT_PERSONAS[expert_id]
    data_context = _build_data_context(expert_id, bracket_context)
    system_prompt = persona["system_prompt"].replace("{data_context}", data_context)

    messages: list[dict[str, str]] = []
    for entry in conversation_history:
        messages.append({"role": entry["role"], "content": entry["content"]})
    messages.append({"role": "user", "content": message})

    async with client.messages.stream(
        model="claude-sonnet-4-20250514",
        max_tokens=1024,
        system=system_prompt,
        messages=messages,
    ) as stream:
        async for text in stream.text_stream:
            yield text


# ---------------------------------------------------------------------------
# Public API — bracket rating
# ---------------------------------------------------------------------------


@dataclass
class BracketRating:
    """Structured result from an expert's bracket evaluation."""

    rating: int
    assessment: str
    suggestions: list[dict[str, str]] = field(default_factory=list)


async def rate_bracket(
    expert_id: str,
    user_bracket: dict[str, str],
    bracket_context: BracketContext,
    client: AsyncAnthropic,
) -> BracketRating:
    """Get an expert's rating of a user's bracket.

    Uses structured XML output parsing to extract a numeric rating,
    prose assessment, and per-game suggestions.

    Args:
        expert_id: Key into ``EXPERT_PERSONAS``.
        user_bracket: Mapping of game slot keys to team names the user picked.
        bracket_context: Model predictions and expert picks for the season.
        client: An initialized ``AsyncAnthropic`` client instance.

    Returns:
        A ``BracketRating`` with the expert's evaluation.
    """
    persona = EXPERT_PERSONAS[expert_id]
    data_context = _build_data_context(expert_id, bracket_context)
    system_prompt = persona["system_prompt"].replace("{data_context}", data_context)

    rating_prompt = (
        "Rate this bracket on a scale of 1-10 and provide your assessment.\n\n"
        "User's bracket picks:\n"
        f"{json.dumps(user_bracket, indent=2)}\n\n"
        "Respond in this exact XML format:\n"
        "<rating>NUMBER</rating>\n"
        "<assessment>Your overall assessment in 2-3 paragraphs</assessment>\n"
        "<suggestions>\n"
        "<suggestion>\n"
        "<game_slot>GAME_SLOT_KEY</game_slot>\n"
        "<current_pick>TEAM_USER_PICKED</current_pick>\n"
        "<suggested_pick>TEAM_YOU_RECOMMEND</suggested_pick>\n"
        "<reasoning>WHY</reasoning>\n"
        "</suggestion>\n"
        "</suggestions>"
    )

    response = await client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=2048,
        system=system_prompt,
        messages=[{"role": "user", "content": rating_prompt}],
    )

    return _parse_rating_response(response.content[0].text)


# ---------------------------------------------------------------------------
# Private — XML response parser
# ---------------------------------------------------------------------------

_RE_RATING = re.compile(r"<rating>\s*(\d+)\s*</rating>", re.DOTALL)
_RE_ASSESSMENT = re.compile(r"<assessment>(.*?)</assessment>", re.DOTALL)
_RE_SUGGESTION = re.compile(r"<suggestion>(.*?)</suggestion>", re.DOTALL)
_RE_TAG = re.compile(r"<(\w+)>(.*?)</\1>", re.DOTALL)


def _parse_rating_response(text: str) -> BracketRating:
    """Parse XML-formatted expert response into a ``BracketRating``.

    Handles malformed XML gracefully by falling back to defaults.
    """
    # Rating
    rating_match = _RE_RATING.search(text)
    rating = int(rating_match.group(1)) if rating_match else 5
    rating = max(1, min(10, rating))

    # Assessment
    assessment_match = _RE_ASSESSMENT.search(text)
    assessment = assessment_match.group(1).strip() if assessment_match else text.strip()

    # Suggestions
    suggestions: list[dict[str, str]] = []
    for suggestion_match in _RE_SUGGESTION.finditer(text):
        block = suggestion_match.group(1)
        suggestion: dict[str, str] = {}
        for tag_match in _RE_TAG.finditer(block):
            tag_name = tag_match.group(1)
            tag_value = tag_match.group(2).strip()
            suggestion[tag_name] = tag_value
        if suggestion:
            suggestions.append(suggestion)

    return BracketRating(
        rating=rating,
        assessment=assessment,
        suggestions=suggestions,
    )
