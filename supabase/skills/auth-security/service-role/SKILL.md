---
description: Service role key — backend only, never in frontend, single client pattern, bypasses RLS for system operations
globs: ["api/**/*.py", "**/*.dart", "**/.env*"]
---

# Service Role

## Context

The Supabase service role key bypasses Row Level Security. It is used
exclusively by the FastAPI backend for system operations — never in Flutter
apps. The backend uses a single service-role client singleton defined in
`api/db.py`.

## Rules

### 1. Service role key is backend-only — never in frontend code

**CORRECT (backend):**

See: `api/db.py`

```python
_client: Client | None = None

def get_supabase_client() -> Client | None:
    """Return a Supabase client using the service role key, or None if not configured."""
    global _client
    if _client is not None:
        return _client

    settings = Settings()
    if not settings.supabase_url or not settings.supabase_service_role_key:
        logger.warning("Supabase URL or service role key not set — DB disabled.")
        return None

    _client = create_client(settings.supabase_url, settings.supabase_service_role_key)
    logger.info("Supabase client initialized (service role).")
    return _client
```

**WRONG (Flutter):**

```dart
// NEVER use service role key in client apps
final client = SupabaseClient(url, serviceRoleKey);
```

### 2. Single client pattern — no anon/service split

March Madness uses a single service-role client (`get_supabase_client()`) for
all backend database operations. The client returns `None` when Supabase is not
configured, enabling JSON-file fallback mode.

| Scenario | What happens |
|----------|-------------|
| Supabase configured | `get_supabase_client()` returns service-role `Client` |
| Supabase not configured | Returns `None` — API falls back to local JSON files |

### 3. Use service role for system operations only

| Operation | Appropriate | Why |
|-----------|------------|-----|
| Seeding teams / predictions | Yes | System data, no user context |
| Inserting expert picks | Yes | Scraped data, no user owner |
| Reading user brackets for admin | Yes | Cross-user access |
| User saving their own bracket | Depends | RLS via Flutter client preferred; backend uses service role + user_id scoping |

### 4. Scope queries by user_id even with service role

Service role bypasses RLS but the backend must still scope queries to the
authenticated user when acting on their behalf.

**CORRECT:**

```python
user_id = get_current_user_id(request)
result = (
    supabase.table("user_brackets")
    .select("*")
    .eq("user_id", user_id)
    .execute()
)
```

**WRONG:**

```python
# Returning ALL user brackets — no user scoping
result = supabase.table("user_brackets").select("*").execute()
```

### 5. Environment variable — never hardcoded

See: `api/config.py`

```python
class Settings(BaseSettings):
    supabase_service_role_key: str = ""  # From .env
```

**WRONG:**

```python
SERVICE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI..."  # Hardcoded secret
```
