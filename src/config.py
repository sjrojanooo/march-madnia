"""Config loader for seasons, features, and bracket data.

Resolves paths relative to PROJECT_ROOT and provides typed accessors
for the config/ directory contents.
"""

from __future__ import annotations

import json
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = PROJECT_ROOT / "config"


def load_seasons(preset_or_list: str | list[int] | None = None) -> list[int]:
    """Return a list of training season ints.

    Parameters
    ----------
    preset_or_list :
        - ``None`` or ``"with2025"`` → default preset
        - A preset name like ``"no2024"``, ``"all"``
        - A list of ints ``[2019, 2021, ...]``
    """
    if isinstance(preset_or_list, list):
        return preset_or_list

    preset_name = preset_or_list or "with2025"
    seasons_path = CONFIG_DIR / "seasons.yaml"
    with open(seasons_path) as f:
        data = yaml.safe_load(f)

    presets = data.get("presets", {})
    if preset_name not in presets:
        raise ValueError(
            f"Unknown season preset '{preset_name}'. "
            f"Available: {list(presets.keys())}"
        )
    return presets[preset_name]["train"]


def load_features(name_or_path: str | None = None) -> list[str] | None:
    """Return a list of feature column names, or None to use all numeric features.

    Parameters
    ----------
    name_or_path :
        - ``None`` or ``"slim"`` → ``config/features/slim_8.txt``
        - ``"all"`` → returns None (use all numeric features)
        - A file path → reads one feature per line from that file
    """
    if name_or_path == "all":
        return None

    if name_or_path is None or name_or_path == "slim":
        feat_path = CONFIG_DIR / "features" / "slim_8.txt"
    else:
        feat_path = Path(name_or_path)
        if not feat_path.is_absolute():
            feat_path = PROJECT_ROOT / feat_path

    if not feat_path.exists():
        raise FileNotFoundError(f"Feature file not found: {feat_path}")

    return [
        line.strip()
        for line in feat_path.read_text().splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]


def load_bracket(season_or_path: int | str | None = None) -> dict:
    """Load a bracket JSON file.

    Parameters
    ----------
    season_or_path :
        - An int like ``2026`` → ``config/brackets/bracket_2026.json``
        - A file path string → loads that JSON directly
        - ``None`` → defaults to 2026
    """
    if season_or_path is None:
        season_or_path = 2026

    if isinstance(season_or_path, int):
        bracket_path = CONFIG_DIR / "brackets" / f"bracket_{season_or_path}.json"
    else:
        bracket_path = Path(season_or_path)
        if not bracket_path.is_absolute():
            bracket_path = PROJECT_ROOT / bracket_path

    if not bracket_path.exists():
        raise FileNotFoundError(f"Bracket file not found: {bracket_path}")

    with open(bracket_path) as f:
        data = json.load(f)

    # Normalize string-keyed seeds to int-keyed for compatibility
    if "regions" in data:
        for region_name, seeds in data["regions"].items():
            data["regions"][region_name] = {
                int(k): v for k, v in seeds.items()
            }

    return data


def load_results(season_or_path: int | str | None = None) -> dict:
    """Load actual tournament results JSON.

    Parameters
    ----------
    season_or_path :
        - An int like ``2025`` → ``config/brackets/results_2025.json``
        - A file path string → loads that JSON directly
    """
    if isinstance(season_or_path, int):
        results_path = CONFIG_DIR / "brackets" / f"results_{season_or_path}.json"
    else:
        results_path = Path(str(season_or_path))
        if not results_path.is_absolute():
            results_path = PROJECT_ROOT / results_path

    if not results_path.exists():
        raise FileNotFoundError(f"Results file not found: {results_path}")

    with open(results_path) as f:
        return json.load(f)
