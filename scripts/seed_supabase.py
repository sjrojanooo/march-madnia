"""Seed Supabase tables from local data files.

Usage: uv run python scripts/seed_supabase.py
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from api.db import get_supabase_client  # noqa: E402


def seed_teams() -> int:
    """Seed teams table from team_features.parquet."""
    import pandas as pd

    path = PROJECT_ROOT / "data" / "processed" / "team_features.parquet"
    if not path.exists():
        logger.warning("team_features.parquet not found — skipping teams seed.")
        return 0

    sb = get_supabase_client()
    if not sb:
        return 0

    df = pd.read_parquet(path).reset_index()
    # Map parquet columns to DB columns
    col_map = {
        "team": "slug",
        "season": "season",
        "adj_eff_margin": "srs",
        "adj_off_eff": "off_rtg",
        "tempo": "pace",
        "conf_win_pct": "conf_win_pct",
    }
    available = {k: v for k, v in col_map.items() if k in df.columns}
    subset = df[list(available.keys())].rename(columns=available)
    # display_name defaults to slug (titlecased) when not available
    subset["display_name"] = subset["slug"].str.replace("-", " ").str.title()

    # Convert NaN to None for JSON serialization
    records = subset.where(subset.notna(), None).to_dict("records")

    # Batch upsert (Supabase limit ~1000 per request)
    batch_size = 500
    count = 0
    for i in range(0, len(records), batch_size):
        batch = records[i : i + batch_size]
        sb.table("teams").upsert(batch, on_conflict="slug,season").execute()
        count += len(batch)
    return count


def seed_predictions() -> int:
    """Seed bracket_predictions from bracket_predictions.json."""
    path = PROJECT_ROOT / "data" / "predictions" / "bracket_predictions.json"
    if not path.exists():
        logger.warning("bracket_predictions.json not found — skipping predictions seed.")
        return 0

    sb = get_supabase_client()
    if not sb:
        return 0

    with open(path) as f:
        data = json.load(f)

    records = []
    # best_bracket is {game_slot: winner_slug}
    best_bracket = data.get("best_bracket", {})
    # game_predictions has per-game probabilities
    game_preds = data.get("game_predictions", {})
    for slot, winner in best_bracket.items():
        prob = 0.5
        if slot in game_preds and isinstance(game_preds[slot], dict):
            prob = game_preds[slot].get("win_probability", game_preds[slot].get("probability", 0.5))
        records.append({
            "season": 2026,
            "game_slot": slot,
            "winner": winner,
            "win_probability": prob,
        })

    if records:
        sb.table("bracket_predictions").upsert(
            records, on_conflict="season,game_slot,model_version"
        ).execute()
    return len(records)


def seed_experts() -> int:
    """Seed expert_picks from expert_picks.json."""
    path = PROJECT_ROOT / "data" / "predictions" / "expert_picks_manual.json"
    if not path.exists():
        logger.warning("expert_picks_manual.json not found — skipping experts seed.")
        return 0

    sb = get_supabase_client()
    if not sb:
        return 0

    with open(path) as f:
        data = json.load(f)

    experts_raw = data.get("experts", data)
    records = []
    if isinstance(experts_raw, dict):
        # {expert_id: {expert_name, source, champion, ...}}
        for eid, info in experts_raw.items():
            records.append({
                "expert_id": eid,
                "expert_name": info.get("expert_name", eid),
                "source": info.get("source", ""),
                "season": 2026,
                "champion": info.get("champion", ""),
                "final_four": info.get("final_four", []),
                "elite_8": info.get("elite_8", []),
                "picks": info.get("picks_by_round", info.get("picks", {})),
            })
    elif isinstance(experts_raw, list):
        for e in experts_raw:
            records.append({
                "expert_id": e.get("expert_id", e.get("id", "")),
                "expert_name": e.get("expert_name", e.get("name", "")),
                "source": e.get("source", ""),
                "season": 2026,
                "champion": e.get("champion", ""),
                "final_four": e.get("final_four", []),
                "elite_8": e.get("elite_8", []),
                "picks": e.get("picks_by_round", e.get("picks", {})),
            })

    if records:
        sb.table("expert_picks").upsert(
            records, on_conflict="expert_id,season"
        ).execute()
    return len(records)


def main() -> None:
    sb = get_supabase_client()
    if not sb:
        logger.error("Cannot connect to Supabase. Check SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY in .env")
        sys.exit(1)

    logger.info("Seeding teams...")
    n = seed_teams()
    logger.info("  → %d teams upserted.", n)

    logger.info("Seeding predictions...")
    n = seed_predictions()
    logger.info("  → %d predictions upserted.", n)

    logger.info("Seeding experts...")
    n = seed_experts()
    logger.info("  → %d experts upserted.", n)

    logger.info("Done!")


if __name__ == "__main__":
    main()
