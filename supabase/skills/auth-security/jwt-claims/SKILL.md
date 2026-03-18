---
description: JWT claims — sub claim for user ID, HS256 validation, backend auth pattern
globs: ["api/**/*.py", "**/*.dart"]
---

# JWT Claims

## Context

Supabase issues JWTs with standard claims. The FastAPI backend extracts `sub`
(user ID) from the token and validates it using the shared `JWT_SECRET`. There
are no custom claims or role resolution — authorization is simple: either the
user owns the resource or they don't.

See: `api/auth.py`

## Rules

### 1. `sub` claim is the user ID — always validate it

```python
# From api/auth.py
payload = jwt.decode(
    token,
    settings.jwt_secret,
    algorithms=["HS256"],
    audience="authenticated",
)
user_id = payload.get("sub")
if not user_id:
    raise HTTPException(status_code=401, detail="Invalid token: no subject.")
```

**WRONG:**

```python
# Trusting sub without validation
user_id = payload["sub"]  # KeyError if missing, no validation
```

### 2. HS256 only — no algorithm negotiation

The backend uses HS256 exclusively with the Supabase JWT secret. There is no
JWKS or ES256 fallback.

```python
payload = jwt.decode(
    token,
    settings.jwt_secret,
    algorithms=["HS256"],
    audience="authenticated",
)
```

**WRONG:**

```python
# Accepting multiple algorithms without verification
payload = jwt.decode(token, key, algorithms=["HS256", "RS256", "none"])
```

### 3. Never decode JWTs on the client

The Flutter app never decodes or inspects JWT contents. It passes the
`accessToken` to the backend as an opaque string.

**WRONG:**

```dart
final payload = JwtDecoder.decode(session.accessToken);
final userId = payload['sub'];
```

**CORRECT:**

```dart
// Pass token to backend — let the server validate
final response = await http.get(
  Uri.parse('$apiUrl/brackets'),
  headers: {'Authorization': 'Bearer ${session.accessToken}'},
);
```

### 4. Authorization is ownership-based — no roles

March Madness does not use role-based access. The backend checks
`auth.uid() = user_id` via RLS, or the `get_current_user_id()` dependency
extracts the user ID for application-level checks.

```python
# api/auth.py — used as a FastAPI dependency
user_id = get_current_user_id(request)
# Then use user_id to scope queries
```

### 5. `app_metadata` vs `user_metadata`

| Field | Who can write | Use case |
|---|---|---|
| `app_metadata` | Service role only | System flags (not currently used) |
| `user_metadata` | User via auth API | Display name, avatar URL |

Never use `user_metadata` for authorization — users can modify it.
