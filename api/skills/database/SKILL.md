---
name: Supabase Database
description: "Use this skill when writing Supabase queries, implementing the JSON fallback pattern, scoping queries to a user, inserting or upserting rows, or accessing the service role client. Trigger phrases: 'query the database', 'add a Supabase query', 'scope this to the user', 'JSON fallback', 'upsert this row', 'check if DB is available', 'database pattern'."
version: 1.0.0
---

# Supabase Database Patterns

## Purpose

Guide all database operations in the March Madness Predictor FastAPI backend.
Follow this skill when writing queries, handling the JSON fallback pattern, or
working with user-scoped data.

---

## Client Setup

A single service-role client is defined in `api/db.py`:

```python
from supabase import Client, create_client
from api.config import Settings

_client: Client | None = None

def get_supabase_client() -> Client | None:
    """Return a Supabase client using the service role key, or None if not configured."""
    global _client
    if _client is not None:
        return _client
    settings = Settings()
    if not settings.supabase_url or not settings.supabase_service_role_key:
        return None
    _client = create_client(settings.supabase_url, settings.supabase_service_role_key)
    return _client
```

### Access Pattern

The client is stored on `app.state` during lifespan startup. Access it via
`request.app.state.supabase` — there is no dependency injection:

```python
# CORRECT — access via app.state
@app.get("/user/brackets")
async def list_user_brackets(request: Request, user_id: str = Depends(get_current_user_id)):
    sb = request.app.state.supabase
    if not sb:
        raise HTTPException(status_code=503, detail="Database not configured.")
    result = sb.table("user_brackets").select("*").eq("user_id", user_id).execute()
    return result.data

# WRONG — importing and calling get_supabase_client() in each endpoint
from api.db import get_supabase_client
sb = get_supabase_client()

# WRONG — using Depends() injection (not how MM is wired)
async def list_brackets(sb: Client = Depends(get_supabase_client)): ...
```

### RLS Implications

The service role client bypasses Row-Level Security. Authorization is
enforced by `get_current_user_id()` + `.eq("user_id", user_id)` filters.

- Every query that touches user data MUST include `.eq("user_id", user_id)`
- Never expose `app.state.supabase` to unauthenticated endpoints for writes
- Public reads (`/bracket`, `/experts`) use JSON file fallback, not Supabase

---

## JSON Fallback Pattern

March Madness is designed to work without Supabase for read-only operations.
Public data is loaded from JSON files at startup:

```python
# In lifespan (api/main.py)
if settings.bracket_predictions_path.exists():
    app.state.bracket_data = json.load(open(settings.bracket_predictions_path))
else:
    app.state.bracket_data = {}

# Supabase is optional
sb = get_supabase_client()
app.state.supabase = sb  # may be None
```

### When Supabase is None

Auth-required endpoints return 503:

```python
# CORRECT — check for None and return 503
sb = request.app.state.supabase
if not sb:
    raise HTTPException(status_code=503, detail="Database not configured.")

# WRONG — assuming sb is always available
result = request.app.state.supabase.table("user_brackets").select("*").execute()
```

Public endpoints fall back to in-memory JSON:

```python
# CORRECT — works without Supabase
@app.get("/bracket")
async def get_bracket(request: Request) -> dict:
    return request.app.state.bracket_data  # loaded from JSON at startup
```

---

## Query Patterns

### Select

```python
# List by user
result = sb.table("user_brackets").select("*").eq("user_id", user_id).order("created_at", desc=True).execute()
brackets = result.data

# Single row by composite key
result = (
    sb.table("chat_history")
    .select("*")
    .eq("user_id", user_id)
    .eq("expert_id", expert_id)
    .execute()
)
if result.data:
    return result.data[0]
```

### Insert

```python
# Single row — returns the inserted row
result = sb.table("user_brackets").insert({
    "user_id": user_id,
    "picks": body.picks,
    "name": body.name,
}).execute()
bracket = result.data[0]
```

### Update

```python
# Update scoped to user
updates = {}
if body.picks is not None:
    updates["picks"] = body.picks
if body.name is not None:
    updates["name"] = body.name
updates["updated_at"] = "now()"

result = (
    sb.table("user_brackets")
    .update(updates)
    .eq("id", bracket_id)
    .eq("user_id", user_id)
    .execute()
)
if not result.data:
    raise HTTPException(status_code=404, detail="Bracket not found.")
```

### Delete

```python
# Delete scoped to user
result = (
    sb.table("user_brackets")
    .delete()
    .eq("id", bracket_id)
    .eq("user_id", user_id)
    .execute()
)
if not result.data:
    raise HTTPException(status_code=404, detail="Bracket not found.")
```

### Upsert

```python
# Upsert with composite conflict key
result = (
    sb.table("chat_history")
    .upsert({
        "user_id": user_id,
        "expert_id": expert_id,
        "messages": body.messages,
        "updated_at": "now()",
    }, on_conflict="user_id,expert_id")
    .execute()
)
```

### Filtering

```python
# Equality
.eq("user_id", user_id)
.eq("expert_id", expert_id)

# Multiple filters (AND)
.eq("bracket_id", bracket_id).eq("user_id", user_id)

# Ordering
.order("created_at", desc=True)
```

---

## No Raw SQL

Never construct SQL strings. Always use the Supabase client methods:

```python
# CORRECT — client methods
sb.table("user_brackets").select("*").eq("user_id", user_id).execute()

# WRONG — string interpolation
sb.table("user_brackets").select("*").filter(f"user_id=eq.{user_id}").execute()

# WRONG — raw SQL
sb.rpc("execute_sql", {"query": f"SELECT * FROM user_brackets WHERE user_id = '{user_id}'"})
```

---

## Database Tables

| Table | RLS | Access Pattern | Notes |
|-------|-----|----------------|-------|
| `teams` | Public read | JSON fallback | Team stats per season |
| `bracket_predictions` | Public read | JSON fallback | Model predictions |
| `expert_picks` | Public read | JSON fallback | Scraped expert picks |
| `user_brackets` | User CRUD own | `get_current_user_id()` + `.eq("user_id", ...)` | Saved user brackets |
| `bracket_ratings` | User read/write own | `get_current_user_id()` + `.eq("user_id", ...)` | Agent ratings |
| `chat_history` | User CRUD own | `get_current_user_id()` + `.eq("user_id", ...)` | Persisted conversations |
| `articles` + `article_embeddings` | Public read | Backend service role | RAG articles with pgvector |

---

## Common Patterns

### Check-then-respond

```python
# Fetch, validate existence, respond
result = (
    sb.table("user_brackets")
    .select("*")
    .eq("id", bracket_id)
    .eq("user_id", user_id)
    .execute()
)
if not result.data:
    raise HTTPException(status_code=404, detail="Bracket not found.")
return result.data[0]
```

### Scoping queries to the user

Always include `.eq("user_id", user_id)` on user-scoped queries to prevent
cross-user data leakage:

```python
# CORRECT — scoped to user
result = sb.table("user_brackets").select("*").eq("user_id", user_id).execute()

# WRONG — missing user scope (returns all users' brackets)
result = sb.table("user_brackets").select("*").execute()
```

---

## Checklist

- [ ] Accesses Supabase via `request.app.state.supabase`
- [ ] Checks for `None` before using Supabase client (503 fallback)
- [ ] No raw SQL or string interpolation
- [ ] User-scoped queries include `.eq("user_id", user_id)`
- [ ] `result.data` checked before indexing
- [ ] Empty update payload returns 400
- [ ] Auth dependency (`get_current_user_id`) paired with every DB write
- [ ] Public read endpoints use JSON fallback (not Supabase)
