# March Madness 2026 Bracket Predictor

ML-powered NCAA March Madness bracket predictor with an ESPN-style web app, AI analyst agents, and expert picks comparison.

## What This Does

- **Predicts the full 63-game bracket** using an ensemble ML model trained on 2019-2025 tournament data
- **Compares predictions with real expert picks** from ESPN, CBS, and Yahoo analysts
- **AI analyst chat** — talk to Claude-powered expert personas about matchups and strategy
- **ESPN-style bracket visualization** — interactive bracket with win probabilities, upset alerts, and pinch-to-zoom

## Architecture

```
├── src/                  # ML pipeline (scraping, features, training, prediction)
├── api/                  # FastAPI backend (predictions API + Claude agent chat)
├── app/                  # Flutter web app (bracket UI, expert picks, chat)
├── supabase/             # PostgreSQL schema + migrations (local dev)
├── scripts/              # Training, scraping, seeding scripts
└── data/                 # Model artifacts + prediction outputs
```

```
Flutter App ──→ FastAPI (port 8000) ──→ Claude API (analyst chat)
                    │
                    ├──→ Supabase DB (port 54321) ──→ PostgreSQL
                    └──→ JSON files (fallback)
```

## Quick Start

### Prerequisites

> **Docker, uv, and Flutter are handled automatically** — `make build` will install any of these that are missing.

The following must be installed before running `make build`:

| Tool | Install |
|------|---------|
| **Python 3.11+** | [python.org](https://www.python.org/) |
| **Node.js 18+** | [nodejs.org](https://nodejs.org/) (for Supabase CLI via npx) |

### 1. Clone and configure

```bash
git clone https://github.com/sjrojanooo/march-madnia.git
cd march-madnia
make setup
```

Edit `.env` and set your Anthropic API key — the only value you need to provide:

```bash
ANTHROPIC_API_KEY=sk-ant-your-key-here
```

All Supabase values are auto-filled when `make build` starts the local DB.

### 2. Build and run

```bash
make build
```

This single command:
1. Creates `.env` and `.dart_defines` if not present
2. Installs `uv` (Python package manager) if not present
3. Installs Flutter SDK and runs `flutter pub get` if not present
4. Installs and starts Docker Desktop if not present
5. Starts Supabase (PostgreSQL + Auth + Studio) and the FastAPI backend
6. Auto-fills `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`, and `JWT_SECRET` into `.env`
7. Seeds the DB — 2,512 teams, 439 bracket predictions, 5 expert picks
8. Launches the Flutter web app at **http://localhost:8080**

Opens Chrome with:
- **Bracket tab** — full ESPN-style tournament bracket with model predictions
- **Experts tab** — dropdown to view each expert's bracket picks
- **Chat tab** — AI analyst agents (requires `ANTHROPIC_API_KEY`)
- **Rate tab** — get your bracket rated by AI experts

## Makefile Commands

| Command | What it does |
|---------|-------------|
| `make build` | Full one-command setup: installs deps → starts services → seeds DB → launches app |
| `make setup` | Creates `.env` and `.dart_defines` from examples |
| `make start` | Starts Supabase + FastAPI backend (Docker must be running) |
| `make stop` | Stops all services |
| `make reset` | Tears down Docker volumes + resets DB with fresh migrations |
| `make seed` | Seeds DB from local prediction/expert data files |
| `make web` | Launches Flutter web app at http://localhost:8080 |
| `make dev` | `make start` + `make seed` (no web, no dependency checks) |
| `make backend` | Rebuilds and restarts just the FastAPI backend container |
| `make logs` | Tail FastAPI backend container logs |
| `make help` | Show all available commands |

## Services & Ports

| Service | URL | Description |
|---------|-----|-------------|
| Flutter Web App | http://localhost:8080 | Bracket UI |
| FastAPI Backend | http://localhost:8000 | REST API + SSE chat |
| Supabase API | http://localhost:54321 | PostgREST + Auth |
| Supabase Studio | http://localhost:54323 | Database admin UI |
| PostgreSQL | localhost:54322 | Direct DB access |
| Mailpit (Inbucket) | http://localhost:54324 | Email testing for auth |

## ML Pipeline

The prediction model is an ensemble (XGBoost + LightGBM + Logistic Regression) trained on 315 tournament games across 5 seasons.

```bash
# Scrape current season data from Sports Reference
uv run python scripts/scrape_season.py --season 2026

# Build features
uv run python -m src.pipeline --stage features

# Train model
uv run python scripts/train.py

# Generate bracket predictions (Monte Carlo simulation)
uv run python scripts/predict.py --season 2026
```

### Model Performance
- **LOSO CV Accuracy**: 75.2%
- **AUC-ROC**: 0.819
- **Brier Score**: 0.192

### Key Features (8 slim features)
| Feature | What it measures |
|---------|-----------------|
| `eff_margin_diff` | Net efficiency differential (dominant predictor) |
| `team_a_adj_eff_margin` | Raw efficiency for team A |
| `team_a_adj_off_eff` | Offensive rating per 100 possessions |
| `team_a_adj_def_eff` | Defensive efficiency proxy |
| `team_b_tempo` | Opponent pace |
| `team_a_seed` | Tournament seed |
| `team_a_rotation_depth` | Roster depth |
| `conf_win_pct_diff` | Conference win rate differential |

## Database Schema

8 tables with Row Level Security:

| Table | Purpose |
|-------|---------|
| `teams` | Team stats per season (public read) |
| `bracket_predictions` | Model predictions (public read) |
| `expert_picks` | Scraped expert picks (public read) |
| `user_brackets` | Saved user brackets (auth required) |
| `bracket_ratings` | AI ratings of brackets (auth required) |
| `articles` | Scraped articles for RAG (public read) |
| `article_embeddings` | pgvector embeddings for search (public read) |
| `chat_history` | Persisted agent conversations (auth required) |

## API Endpoints

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/bracket` | No | Full bracket predictions |
| GET | `/experts` | No | Expert picks data |
| GET | `/agents` | No | List AI analyst agents |
| POST | `/agents/{id}/chat` | No | Chat with agent (SSE stream) |
| POST | `/agents/{id}/rate-bracket` | No | Rate a bracket |
| GET | `/user/brackets` | JWT | List user's saved brackets |
| POST | `/user/brackets` | JWT | Save a bracket |
| PUT | `/user/brackets/{id}` | JWT | Update a bracket |
| DELETE | `/user/brackets/{id}` | JWT | Delete a bracket |
| GET/POST | `/user/chat-history/{expert_id}` | JWT | Get/save chat history |

## Project Structure

```
march-madnia/
├── api/
│   ├── main.py          # FastAPI app, endpoints, lifespan
│   ├── agents.py        # Claude agent chat + bracket rating
│   ├── auth.py          # JWT validation (Supabase tokens)
│   ├── config.py        # Pydantic settings
│   ├── db.py            # Supabase client singleton
│   └── models.py        # Request/response models
├── app/
│   └── lib/
│       ├── main.dart                    # App entry point
│       ├── app.dart                     # Router + shell scaffold
│       ├── core/
│       │   ├── config/app_config.dart   # Env config
│       │   ├── models/                  # Data models
│       │   └── theme/app_theme.dart     # Dark theme
│       ├── data/
│       │   ├── repositories/            # API data access
│       │   └── services/                # API + Supabase services
│       └── features/
│           ├── bracket/                 # ESPN-style bracket UI
│           ├── experts/                 # Expert picks comparison
│           └── agents/                  # AI chat + rating screens
├── src/
│   ├── scraping/        # Sports Reference + expert picks scrapers
│   ├── features/        # Feature engineering (team, matchup, player)
│   ├── models/          # ML models (ensemble, boosting, calibration)
│   ├── bracket/         # Monte Carlo bracket simulator
│   └── agents/          # Claude agent personas
├── scripts/             # Training, prediction, seeding scripts
├── supabase/
│   ├── config.toml      # Local dev config
│   ├── migrations/      # 8 SQL migration files
│   └── seeds/           # Minimal seed data
├── Dockerfile           # FastAPI backend container
├── docker-compose.yml   # Backend service definition
├── Makefile             # Orchestration commands
└── pyproject.toml       # Python dependencies
```

## License

MIT
