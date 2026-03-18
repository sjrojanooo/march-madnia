from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings

PROJECT_ROOT = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    anthropic_api_key: str = ""
    cors_origins: list[str] = ["*"]  # Dev only — restrict in production
    bracket_predictions_path: Path = (
        PROJECT_ROOT / "data" / "predictions" / "bracket_predictions.json"
    )
    expert_picks_path: Path = PROJECT_ROOT / "data" / "predictions" / "expert_picks_manual.json"
    supabase_url: str = ""
    supabase_anon_key: str = ""
    supabase_service_role_key: str = ""
    jwt_secret: str = ""
    model_config = {"env_file": str(PROJECT_ROOT / ".env"), "env_file_encoding": "utf-8"}
