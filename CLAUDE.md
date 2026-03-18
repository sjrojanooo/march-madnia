# March Madness Prediction — Claude Reference

## Project Goal
Predict NCAA March Madness 2026 bracket outcomes using historical tournament data and current-season team statistics. Output: per-game win probabilities + Monte Carlo bracket simulation.

## Season Numbering Convention
- `season=2026` = 2025-26 academic year = **2026 tournament** (what we're predicting)
- `season=2025` = 2024-25 academic year = **2025 tournament** (Florida's championship, used in training)
- Training excludes 2024 (Florida runner-up) to avoid double-Florida bias

## Current Model State
- **Model file**: `data/models/ensemble_with2025.joblib`
- **Feature names**: `data/models/feature_names_with2025.txt`
- **Training seasons**: 2019, 2021, 2022, 2023, 2025 (315 games)
- **LOSO CV accuracy**: 75.2%
- **Train accuracy**: 88.3%
- **AUC-ROC**: 0.819
- **Brier score**: 0.192
- **Live features**: 8 (slim model selected via permutation importance)

## Active Feature Set (8 slim features)
| Feature | Source | What it measures |
|---------|--------|-----------------|
| `eff_margin_diff` | SR SRS (A-B) | Net efficiency differential — dominant predictor |
| `team_a_adj_eff_margin` | SR SRS | Raw efficiency for team A (non-linear scale effects) |
| `team_a_adj_off_eff` | SR off_rtg | Offensive rating per 100 possessions |
| `team_a_adj_def_eff` | SR off_rtg - SRS | Defensive efficiency proxy |
| `team_b_tempo` | SR pace | Opponent pace — slow teams disrupt higher seeds |
| `team_a_seed` | Tournament bracket | Committee judgment (injury/form info stats miss) |
| `team_a_rotation_depth` | Player features | Foul trouble / back-to-back resilience |
| `conf_win_pct_diff` | SR wins_conf (A-B) | Conference win rate — quality of wins |

## Pipeline Stages
```
1. Scrape      → src/scraping/sports_ref.py      → data/raw/*.parquet
2. Features    → src/features/team_features.py   → data/processed/team_features.parquet
               → src/features/matchup.py         → data/processed/matchup_training.parquet
3. Train       → scripts/train_with2025.py       → data/models/ensemble_with2025.joblib
4. Predict     → scripts/predict_bracket.py      → data/predictions/bracket_predictions.*
```

## Key Commands
```bash
# Start full local dev stack (Supabase + backend)
make dev

# Start/stop infrastructure
make start          # Supabase + Docker backend
make stop           # Tear down
make reset          # Full reset with db migrations

# Seed Supabase from local data files
make seed

# Run Flutter web app
make web

# Backend logs
make logs

# Rebuild features after scraping new data
uv run python -m src.pipeline --stage features

# Retrain model
uv run python scripts/train_with2025.py

# Run predictions
uv run python scripts/predict_bracket.py

# Scrape a specific season (extend VALID_SEASONS first)
uv run python -m src.scraping.sports_ref
```

## Known Dead Features (zero variance — do not use)
- `momentum_diff` / `team_a/b_last10_winpct` — broken, defaults to 0.5
- `experience_diff` / `team_a/b_experience_score` — no class-year data scraped
- `quad1_wins_diff` / `team_a/b_quad1_wins` — hardcoded 0.0 (SR doesn't expose this)
- `portal_stability_diff` / `team_a/b_roster_continuity` — no portal data
- `ap_rank_diff` — redundant with seed, actively hurts (-1.0% permutation importance)

## Known Bugs Fixed
- `ap_rankings_all_seasons.parquet` was overwritten to 2026-only on targeted scrape — rebuilt by concatenating per-season files
- Final Four probabilities were double-counted in simulator (region winner + semifinal game) — fixed in `src/bracket/simulator.py:591`
- `conf_win_pct` was computed in team_features but not wired into matchup DIFF_FEATURES/RAW_FEATURE_COLS

## Data Coverage
| Season | Team Stats | AP Rankings | Tournament Results | Notes |
|--------|------------|-------------|-------------------|-------|
| 2010-2018 | **NOT YET SCRAPED** | **NOT YET SCRAPED** | Need to verify | Next priority |
| 2019 | ✅ | ✅ | ✅ | |
| 2020 | — | — | — | No tournament (COVID) |
| 2021-2025 | ✅ | ✅ | ✅ | |
| 2026 | ✅ | ✅ | N/A | Prediction target |

## Planned Features (not yet implemented)
| Feature | Signal | Effort | Status |
|---------|--------|--------|--------|
| Coach tournament wins (by coach, not program) | High | Medium | Pending |
| Senior roster % (experience_score fix) | High | Medium | Pending |
| Geolocation proximity to tournament site | Medium | Medium | Pending |
| Conference strength (mean SRS per conference) | Medium | Low | Pending — add to team_features.py |
| Comeback wins / clutch record | Medium | High | Pending — needs game logs |

## Feature Strategy Notes
- 315 samples → 8 features is the right ratio. Adding features requires more data.
- Extending to 2010-2018 gives ~882 total games — enough to test momentum, experience, coaching
- Conference strength: compute from existing SR data (group by conference, mean SRS per season) rather than re-enabling Torvik
- All features must exist for season=2026 at prediction time — no leakage

## SR → Model Feature Mapping
| SR column | Model feature | Notes |
|-----------|--------------|-------|
| `srs` | `adj_eff_margin` | Net rating adj for schedule |
| `off_rtg` | `adj_off_eff` | Points per 100 possessions |
| `off_rtg - srs` | `adj_def_eff` | Defensive efficiency proxy |
| `pace` | `tempo` | Possessions per 40 min |
| `sos` | `conf_strength` | Schedule strength proxy |
| `wins_conf / (wins_conf + losses_conf)` | `conf_win_pct` | Conference win rate |

## Supabase Local Dev

### Architecture
```
Makefile (orchestration)
  ├── supabase start        → PostgreSQL + Auth + Studio (ports 54321-54323)
  ├── docker compose up     → FastAPI backend (port 8000)
  └── flutter run           → Flutter app (port 8080)

Flutter App ──→ Supabase Auth (direct, PKCE via supabase_flutter)
Flutter App ──→ FastAPI ──→ Supabase DB (service role key)
                       ──→ Claude API (analyst chat)
```

### Database Tables
| Table | RLS | Purpose |
|-------|-----|---------|
| `teams` | Public read | Team stats per season |
| `bracket_predictions` | Public read | Model predictions |
| `expert_picks` | Public read | Scraped expert picks |
| `user_brackets` | User CRUD own | Saved user brackets |
| `bracket_ratings` | User read/write own | Agent ratings of brackets |
| `articles` + `article_embeddings` | Public read | RAG articles with pgvector |
| `chat_history` | User CRUD own | Persisted agent conversations |

### Key Design Decisions
- ML pipeline untouched — Supabase serves API/app layer only
- JSON fallback — API works without Supabase running (backward compatible)
- Auth via Supabase directly — Flutter uses PKCE; backend validates JWT
- Service role key for backend DB access (bypasses RLS)
- HNSW index for vector search (works without pre-existing data)
