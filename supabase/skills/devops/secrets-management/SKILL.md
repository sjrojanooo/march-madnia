---
description: Secrets management — env vars, no secrets in migrations, key rotation, Settings class
globs: ["**/.env*", "api/**/*.py", "supabase/functions/**/*.ts", "supabase/migrations/**/*.sql"]
---

# Secrets Management

## Context

Secrets (API keys, service role keys, JWT secrets) are managed via environment
variables loaded by pydantic-settings. They are never hardcoded in source code
or included in migrations.

See: `api/config.py` — the `Settings` class loads all secrets from `.env`.

## Rules

### 1. No secrets in migrations

Migrations are version-controlled. Never include API keys, tokens, or
passwords in SQL files.

**WRONG:**

```sql
-- Hardcoded API key in migration
INSERT INTO settings (key, value)
VALUES ('anthropic_key', 'sk-ant-xxx');
```

**CORRECT:**

```sql
-- Reference via Vault or leave for application layer
-- API keys are set in .env / Supabase dashboard
```

### 2. Use .env files — never commit them

```bash
# .env (gitignored)
SUPABASE_URL=http://127.0.0.1:54321
SUPABASE_ANON_KEY=eyJ...
SUPABASE_SERVICE_ROLE_KEY=eyJ...
JWT_SECRET=super-secret-jwt-token
ANTHROPIC_API_KEY=sk-ant-xxx
```

The `Settings` class in `api/config.py` loads these automatically:

```python
class Settings(BaseSettings):
    anthropic_api_key: str = ""
    supabase_url: str = ""
    supabase_anon_key: str = ""
    supabase_service_role_key: str = ""
    jwt_secret: str = ""
    model_config = {"env_file": str(PROJECT_ROOT / ".env"), "env_file_encoding": "utf-8"}
```

Always provide `.env.example` with placeholder values:

```bash
# .env.example (committed)
SUPABASE_URL=http://127.0.0.1:54321
SUPABASE_ANON_KEY=<your-anon-key>
SUPABASE_SERVICE_ROLE_KEY=<your-service-role-key>
JWT_SECRET=<your-jwt-secret>
ANTHROPIC_API_KEY=<your-anthropic-api-key>
```

### 3. Edge Function secrets via CLI

```bash
supabase secrets set ANTHROPIC_API_KEY=sk-ant-xxx
```

Access in functions:

```typescript
const apiKey = Deno.env.get('ANTHROPIC_API_KEY')
```

### 4. Files that must never be committed

- `.env`, `.env.local`, `.env.*` (except `.env.example`)
- `.dart_defines` (Flutter compile-time secrets)
- `google-services.json`, `GoogleService-Info.plist`
- `firebase_options.dart`
- `*.pem`, `*.key`, `id_rsa`, `id_ed25519`
- `*-service-account*.json`

### 5. Rotate keys when compromised

If a key is accidentally committed:
1. Rotate it immediately via Supabase dashboard (or Anthropic console for API keys)
2. Update `.env` files in all environments
3. Redeploy affected services
4. Scrub the key from git history (BFG Repo Cleaner)

### 6. Supabase Vault for database-level secrets

Use Supabase Vault for secrets that PostgreSQL functions need at runtime
(e.g., external API keys for triggers).

```sql
-- Store in Vault
SELECT vault.create_secret('anthropic_key', 'sk-ant-xxx');

-- Access in function
SELECT decrypted_secret FROM vault.decrypted_secrets
WHERE name = 'anthropic_key';
```
