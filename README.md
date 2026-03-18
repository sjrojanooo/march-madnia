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

| Tool | Install |
|------|---------|
| **Python 3.11+** | [python.org](https://www.python.org/) |
| **uv** | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| **Flutter 3.10+** | [flutter.dev/docs/get-started](https://flutter.dev/docs/get-started/install) |
| **Docker** | [docker.com](https://www.docker.com/get-started/) |
| **Node.js 18+** | [nodejs.org](https://nodejs.org/) (for Supabase CLI via npx) |

### 1. Clone and setup

```bash
git clone https://github.com/sjrojanooo/march-madnia.git
cd march-madnia

# Install Python dependencies
uv sync

# Install Flutter dependencies
cd app && flutter pub get && cd ..

# Create config files from examples
make setup
```

### 2. Configure environment

Edit `.env` with your keys:

```bash
# Required for AI chat (get from https://console.anthropic.com/)
ANTHROPIC_API_KEY=sk-ant-your-key-here

# These are auto-filled when Supabase starts (step 3)
SUPABASE_URL=http://127.0.0.1:54321
SUPABASE_ANON_KEY=
SUPABASE_SERVICE_ROLE_KEY=
JWT_SECRET=
```

### 3. Start everything

```bash
# Start Supabase (PostgreSQL + Auth + Studio) and the FastAPI backend
make start
```

This will:
- Pull Docker images for Supabase services (first run takes a few minutes)
- Apply all database migrations (8 tables including teams, predictions, expert picks)
- Run SQL seeds
- Build and start the FastAPI backend container

After it completes, grab the Supabase keys from the output and paste them into `.env`:
```bash
# Get the keys
npx supabase status
```

### 4. Seed the database

```bash
make seed
```

Loads 2,512 teams, 439 bracket predictions, and 5 expert picks into PostgreSQL.

### 5. Launch the web app

```bash
make web
```

Opens Chrome at **http://localhost:8080** with:
- **Bracket tab** — full ESPN-style tournament bracket with model predictions
- **Experts tab** — dropdown to view each expert's bracket picks
- **Chat tab** — AI analyst agents (requires `ANTHROPIC_API_KEY`)
- **Rate tab** — get your bracket rated by AI experts

### All-in-one

```bash
make dev   # runs: make start && make seed
make web   # in a separate terminal
```

## Makefile Commands

| Command | What it does |
|---------|-------------|
| `make setup` | Creates `.env` and `.dart_defines` from examples |
| `make start` | Starts Supabase + FastAPI backend |
| `make stop` | Stops everything |
| `make reset` | Full teardown + fresh DB with migrations and seeds |
| `make seed` | Seeds DB from local prediction/expert data files |
| `make web` | Launches Flutter web app on port 8080 |
| `make dev` | `make start` + `make seed` |
| `make backend` | Rebuilds and restarts just the backend container |
| `make logs` | Tail backend container logs |

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
uv run python -m src.scraping.sports_ref

# Build features
uv run python -m src.pipeline --stage features

# Train model
uv run python scripts/train_with2025.py

# Generate bracket predictions (Monte Carlo simulation)
uv run python scripts/predict_bracket.py
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
