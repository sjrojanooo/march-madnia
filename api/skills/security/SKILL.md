---
name: FastAPI Security
description: "Use this skill when writing new API endpoints, reviewing authentication code, auditing for OWASP vulnerabilities, adding JWT validation, or hardening the FastAPI backend. Trigger phrases: 'secure this endpoint', 'add auth', 'check for vulnerabilities', 'review security', 'OWASP checklist', 'JWT validation', 'protect this route', 'audit backend security'."
version: 1.0.0
---

# FastAPI Security Best Practices

## Purpose

Enforce security best practices across the March Madness Predictor FastAPI
backend. Apply this skill when writing new endpoints, reviewing existing code,
or auditing for vulnerabilities.

---

## Authentication

### JWT Validation

- All JWT validation lives in `api/auth.py` via `get_current_user_id()` — never inline
- HS256-only using `python-jose` — token signed with Supabase `JWT_SECRET`
- Always validate token expiration (`exp` claim)
- Always validate `audience="authenticated"` (Supabase convention)
- Extract `sub` claim as user ID
- Return 401 on failure — never expose token content in error responses

```python
# CORRECT — use the dependency from api/auth.py
from api.auth import get_current_user_id

@app.get("/user/brackets")
async def list_user_brackets(
    request: Request,
    user_id: str = Depends(get_current_user_id),
): ...

# WRONG — inline JWT parsing
token = request.headers.get("Authorization", "").removeprefix("Bearer ")
payload = jwt.decode(token, secret, algorithms=["HS256"])
```

```python
# CORRECT — structured error, no token details
raise HTTPException(status_code=401, detail="Invalid or expired token.")

# WRONG — exposes token details
raise HTTPException(400, detail=f"Invalid token: {token}")
```

### Auth Dependency Pattern

March Madness uses a simple user-scoped auth model (no roles, no orgs):

- `get_current_user_id(request)` extracts and validates the JWT
- Returns the `sub` claim as a `str` user ID
- Used as a FastAPI `Depends()` on all `/user/*` endpoints
- Public endpoints (`/bracket`, `/experts`, `/agents`) do not require auth

---

## Input Validation

### Pydantic Models

- All request/response schemas live in `api/models.py`
- Use `Field(...)` with constraints (`min_length`, `max_length`, `ge`, `le`)
- Use separate Create/Update/Response schemas — never reuse

```python
# CORRECT — constrained fields (from api/models.py)
class AgentChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)
    conversation_history: list[dict[str, str]] = Field(default_factory=list)

# WRONG — accepting any string with no constraints
class AgentChatRequest(BaseModel):
    message: str  # No length validation
```

### Path Parameters

- `expert_id` and `bracket_id` are string IDs — validate against known values
- Use helper functions like `_validate_expert_id()` in `api/main.py`
- Never trust path parameters without validation

### Request Body Size

- Rely on reverse proxy (nginx/Cloudflare) for request size limits
- `conversation_history` could grow large — consider adding max length validation

---

## Injection Prevention

### SQL Injection

- Never construct raw SQL strings — always use Supabase client methods
- Use parameterized queries via `.eq()`, `.in_()`, `.is_()` etc.
- Never interpolate user input into `.rpc()` function names

```python
# CORRECT — parameterized via Supabase client
sb.table("user_brackets").select("*").eq("user_id", user_id).execute()

# WRONG — string interpolation
sb.table("user_brackets").select("*").filter(f"user_id=eq.{user_id}").execute()
```

### Command Injection

- Never pass user input to shell commands, `subprocess`, or `eval`
- Never use user input in file paths without sanitization
- This backend has no shell execution — keep it that way

### XSS Prevention

- API returns JSON only — no HTML rendering
- Pydantic models strip/validate all string inputs
- Frontend (Flutter) handles rendering — no server-side templates

---

## Data Protection

### Secrets Management

- All secrets via environment variables (`pydantic-settings` in `api/config.py`)
- Never hardcode keys, passwords, or URLs
- Never log secrets — use `repr()` or masked output
- Required secrets:
  - `ANTHROPIC_API_KEY` — Claude API access for agent chat/rating
  - `SUPABASE_URL` — local or remote Supabase instance
  - `SUPABASE_SERVICE_ROLE_KEY` — bypasses RLS (backend only)
  - `SUPABASE_ANON_KEY` — public client key
  - `JWT_SECRET` — Supabase JWT signing secret
- Files that must never be committed: `.env`, `*.pem`, `*.key`,
  `*-service-account*.json`, `google-services.json`

### Anthropic API Key

- Must come from environment (`Settings.anthropic_api_key` in `api/config.py`)
- Never accept from request bodies, query params, or headers
- If not configured, agent endpoints return 503 (see `_require_anthropic()`)
- Never log the key value

---

## API Security

### CORS

- Configured in `api/main.py` — `settings.cors_origins`
- `["*"]` is dev-only — restrict to known origins in production
- Current config allows all origins for local development

### Rate Limiting

**Not yet implemented — should add:**
- `/agents/{expert_id}/chat`: 10 requests per user per minute
- `/agents/{expert_id}/rate-bracket`: 5 requests per user per minute
- `/user/brackets`: 20 requests per user per minute
- Use middleware or API gateway (nginx, Cloudflare)

### Error Handling

- Use structured `detail` dicts — never bare strings for machine-readable errors
- Never expose stack traces, database errors, or internal state
- Current pattern uses `HTTPException(detail=dict)` directly (no custom exception classes yet)

```python
# CORRECT — structured error dict
raise HTTPException(
    status_code=503,
    detail={
        "error": "anthropic_unavailable",
        "message": "ANTHROPIC_API_KEY is not configured.",
    },
)

# WRONG — exposes internal details
raise HTTPException(500, detail=str(e))
```

### Request/Response Headers

**Should add in production:**
- `Strict-Transport-Security: max-age=31536000; includeSubDomains`
- `X-Content-Type-Options: nosniff`
- `X-Frame-Options: DENY`
- `Content-Security-Policy: default-src 'self'`
- `Cache-Control: no-store` on authenticated responses

---

## Database Security (Supabase/PostgreSQL)

### Row-Level Security

- Every table has RLS enabled
- Backend uses service role client (`api/db.py`) which bypasses RLS
- Authorization enforced by `get_current_user_id()` dependency + `.eq("user_id", user_id)` filters
- Always scope user data queries with `.eq("user_id", user_id)`

### JSON Fallback

- When Supabase is not configured, `app.state.supabase` is `None`
- Public endpoints (`/bracket`, `/experts`) fall back to JSON files on disk
- Auth-required endpoints return 503 when DB is unavailable

### Migration Safety

- Migrations must be idempotent (`IF NOT EXISTS`, `ON CONFLICT DO NOTHING`)
- Never `DROP TABLE` without explicit confirmation
- All timestamps: `timestamptz` (never bare `timestamp`)

---

## SSE Security

- SSE streams (`/agents/{expert_id}/chat`) must handle `asyncio.CancelledError`
- Error payloads in SSE use `{"chunk": "", "done": true, "error": "..."}` — never expose stack traces
- Client disconnects are logged at INFO level, not ERROR

---

## OWASP Top 10 Checklist

| # | Risk | Status | Notes |
|---|------|--------|-------|
| A01 | Broken Access Control | Mitigated | JWT auth + user_id scoping on all /user/* endpoints |
| A02 | Cryptographic Failures | Mitigated | Supabase handles encryption, JWT via HS256 |
| A03 | Injection | Mitigated | Supabase client (no raw SQL), Pydantic validation |
| A04 | Insecure Design | Partial | Need rate limiting on agent endpoints |
| A05 | Security Misconfiguration | Partial | Need production security headers, restrict CORS |
| A06 | Vulnerable Components | Monitor | Use `uv audit` regularly |
| A07 | Auth Failures | Mitigated | JWT validation, token expiry, Supabase Auth |
| A08 | Data Integrity | Mitigated | Pydantic validation, DB constraints |
| A09 | Logging Failures | Partial | Need structured logging |
| A10 | SSRF | Low risk | Anthropic API is only outbound call; no user-controlled URLs |

---

## Security Review Checklist

When reviewing any FastAPI endpoint, verify:

- [ ] Uses `get_current_user_id()` dependency for user-scoped endpoints
- [ ] Request body uses Pydantic model with proper constraints
- [ ] No raw SQL or string interpolation in queries
- [ ] Error responses don't expose internal details (no `str(e)`)
- [ ] No secrets or PII in log statements
- [ ] Response model excludes sensitive fields
- [ ] User data queries scoped with `.eq("user_id", user_id)`
- [ ] SSE streams handle `CancelledError` gracefully
- [ ] `ANTHROPIC_API_KEY` comes from `Settings`, never from request input
- [ ] Supabase unavailability returns 503, not 500
