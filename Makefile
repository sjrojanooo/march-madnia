.PHONY: setup start stop reset backend seed web dev logs

setup:
	@test -f .env || cp .env.example .env && echo "Created .env from .env.example"
	@test -f .dart_defines || cp .dart_defines.example .dart_defines && echo "Created .dart_defines from .dart_defines.example"

start:
	npx supabase stop --no-backup
	npx supabase start
	docker compose up -d --build

stop:
	docker compose down
	npx supabase stop --no-backup

reset:
	docker compose down -v
	npx supabase stop
	npx supabase start
	npx supabase db reset

backend:
	docker compose up -d --build backend

seed:
	uv run python scripts/seed_supabase.py

web:
	cd app && flutter run -d chrome --web-port 8080 --dart-define-from-file=../.dart_defines

dev: start seed

logs:
	docker compose logs -f backend
