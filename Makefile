.PHONY: setup start stop reset backend seed web dev build logs ensure-docker ensure-uv ensure-flutter help env-autofill

ensure-uv:
	@if ! command -v uv &>/dev/null; then \
		echo "uv not found. Installing..."; \
		curl -LsSf https://astral.sh/uv/install.sh | sh; \
		echo "uv installed. You may need to restart your shell if this is your first install."; \
	else \
		echo "uv is installed."; \
	fi

ensure-flutter:
	@if ! command -v flutter &>/dev/null; then \
		echo "Flutter not found. Installing Flutter..."; \
		ARCH=$$(uname -m); \
		if [ "$$ARCH" = "arm64" ]; then \
			FLUTTER_URL="https://storage.googleapis.com/flutter_infra_release/releases/stable/macos/flutter_macos_arm64_3.24.5-stable.zip"; \
		else \
			FLUTTER_URL="https://storage.googleapis.com/flutter_infra_release/releases/stable/macos/flutter_macos_3.24.5-stable.zip"; \
		fi; \
		echo "Downloading Flutter SDK..."; \
		curl -L --progress-bar "$$FLUTTER_URL" -o /tmp/flutter.zip; \
		echo "Extracting to ~/flutter..."; \
		unzip -q /tmp/flutter.zip -d ~/; \
		rm /tmp/flutter.zip; \
		echo "Adding Flutter to PATH in ~/.zshrc..."; \
		grep -qxF 'export PATH="$$HOME/flutter/bin:$$PATH"' ~/.zshrc || echo 'export PATH="$$HOME/flutter/bin:$$PATH"' >> ~/.zshrc; \
		export PATH="$$HOME/flutter/bin:$$PATH"; \
		echo "Running flutter pub get..."; \
		cd app && yes | $$HOME/flutter/bin/flutter pub get && cd ..; \
		echo "Flutter installed. Restart your shell or run: export PATH=\"\$$HOME/flutter/bin:\$$PATH\""; \
	else \
		echo "Flutter is installed."; \
		if [ ! -d app/build ] || [ ! -f app/.dart_tool/package_config.json ]; then \
			echo "Running flutter pub get..."; \
			cd app && yes | flutter pub get && cd ..; \
		fi; \
	fi

ensure-docker:
	@if ! command -v docker &>/dev/null; then \
		echo "Docker not found. Downloading Docker Desktop..."; \
		ARCH=$$(uname -m); \
		if [ "$$ARCH" = "arm64" ]; then \
			URL="https://desktop.docker.com/mac/main/arm64/Docker.dmg"; \
		else \
			URL="https://desktop.docker.com/mac/main/amd64/Docker.dmg"; \
		fi; \
		curl -L --progress-bar "$$URL" -o /tmp/Docker.dmg; \
		echo "Mounting Docker.dmg..."; \
		hdiutil attach /tmp/Docker.dmg -quiet; \
		echo "Installing Docker.app to /Applications (may prompt for password)..."; \
		sudo cp -R /Volumes/Docker/Docker.app /Applications/; \
		hdiutil detach /Volumes/Docker -quiet; \
		rm /tmp/Docker.dmg; \
		echo "Launching Docker Desktop..."; \
		open /Applications/Docker.app; \
		echo "Waiting for Docker daemon to be ready (this may take ~30s on first launch)..."; \
		until docker info &>/dev/null 2>&1; do printf '.'; sleep 2; done; \
		echo "\nDocker is ready."; \
	elif ! docker info &>/dev/null 2>&1; then \
		echo "Docker is installed but not running. Starting Docker Desktop..."; \
		open /Applications/Docker.app; \
		echo "Waiting for Docker daemon..."; \
		until docker info &>/dev/null 2>&1; do printf '.'; sleep 2; done; \
		echo "\nDocker is ready."; \
	else \
		echo "Docker is running."; \
	fi

env-autofill:
	@echo "Reading Supabase credentials and updating .env..."
	@STATUS=$$(npx supabase status 2>/dev/null); \
	ANON_KEY=$$(echo "$$STATUS" | grep 'anon key' | awk '{print $$NF}'); \
	SERVICE_KEY=$$(echo "$$STATUS" | grep 'service_role key' | awk '{print $$NF}'); \
	JWT=$$(echo "$$STATUS" | grep 'JWT secret' | awk '{print $$NF}'); \
	sed -i '' "s|SUPABASE_URL=.*|SUPABASE_URL=http://localhost:54321|" .env; \
	sed -i '' "s|SUPABASE_ANON_KEY=.*|SUPABASE_ANON_KEY=$$ANON_KEY|" .env; \
	sed -i '' "s|SUPABASE_SERVICE_ROLE_KEY=.*|SUPABASE_SERVICE_ROLE_KEY=$$SERVICE_KEY|" .env; \
	sed -i '' "s|JWT_SECRET=.*|JWT_SECRET=$$JWT|" .env; \
	echo ".env updated with local Supabase credentials."

setup:
	@test -f .env || cp .env.example .env && echo "Created .env from .env.example"
	@test -f .dart_defines || cp .dart_defines.example .dart_defines && echo "Created .dart_defines from .dart_defines.example"

start:
	npx supabase stop --no-backup
	npx supabase start
	$(MAKE) env-autofill
	docker compose up -d --build

stop:
	docker compose down
	npx supabase stop --no-backup

reset:
	docker compose down -v
	npx supabase db reset

backend:
	docker compose up -d --build backend

seed:
	uv run python scripts/seed_supabase.py

web:
	cd app && flutter run -d chrome --web-port 8080 --dart-define-from-file=../.dart_defines

dev: start seed

build: setup ensure-uv ensure-flutter ensure-docker start seed web

logs:
	docker compose logs -f backend

help:
	@printf "\n\033[1;36m  March Madness 2026 — Available Commands\033[0m\n"
	@printf "\033[90m  ════════════════════════════════════════\033[0m\n\n"
	@printf "\033[1;33m  Setup & Run\033[0m\n"
	@printf "  \033[1;32mmake build\033[0m          \033[37mFull one-command setup: installs deps, starts services, seeds DB, launches app\033[0m\n"
	@printf "  \033[1;32mmake setup\033[0m          \033[37mCreates .env and .dart_defines config files from examples\033[0m\n"
	@printf "  \033[1;32mmake env-autofill\033[0m   \033[37mAuto-fills Supabase keys into .env after Supabase starts\033[0m\n\n"
	@printf "\033[1;33m  Services\033[0m\n"
	@printf "  \033[1;32mmake start\033[0m          \033[37mStarts Supabase + FastAPI backend (Docker must be running)\033[0m\n"
	@printf "  \033[1;32mmake stop\033[0m           \033[37mStops all services (Supabase + Docker backend)\033[0m\n"
	@printf "  \033[1;32mmake reset\033[0m          \033[37mFull teardown and fresh DB with migrations and seeds\033[0m\n"
	@printf "  \033[1;32mmake seed\033[0m           \033[37mSeeds the DB with teams, predictions, and expert picks\033[0m\n"
	@printf "  \033[1;32mmake web\033[0m            \033[37mLaunches the Flutter web app at http://localhost:8080\033[0m\n"
	@printf "  \033[1;32mmake dev\033[0m            \033[37mRuns make start + make seed (no web, no dependency checks)\033[0m\n"
	@printf "  \033[1;32mmake backend\033[0m        \033[37mRebuilds and restarts just the FastAPI backend container\033[0m\n"
	@printf "  \033[1;32mmake logs\033[0m           \033[37mTail FastAPI backend container logs\033[0m\n\n"
	@printf "\033[1;33m  Dependency Checks\033[0m\n"
	@printf "  \033[1;32mmake ensure-uv\033[0m      \033[37mInstalls uv (Python package manager) if not found\033[0m\n"
	@printf "  \033[1;32mmake ensure-flutter\033[0m \033[37mInstalls Flutter SDK and runs flutter pub get if not found\033[0m\n"
	@printf "  \033[1;32mmake ensure-docker\033[0m  \033[37mInstalls and starts Docker Desktop if not found or not running\033[0m\n\n"
	@printf "\033[1;33m  Other\033[0m\n"
	@printf "  \033[1;32mmake help\033[0m           \033[37mShow this help message\033[0m\n\n"
