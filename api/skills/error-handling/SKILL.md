---
name: Error Handling
description: "Use this skill when raising HTTPExceptions, creating structured error responses, handling validation errors, formatting SSE error payloads, or adding custom exception classes. Trigger phrases: 'handle this error', 'add error handling', 'return a 404', 'structured error response', 'SSE error payload', 'create exception class', 'fix error format'."
version: 1.0.0
---

# Error Handling Patterns

## Purpose

Guide consistent error handling across the March Madness Predictor FastAPI
backend. Follow this skill when raising errors from endpoints, handling
validation failures, or streaming error payloads via SSE.

---

## Current Pattern: Inline HTTPException

March Madness does not yet have custom exception classes. All errors are raised
as `HTTPException` with structured `detail` dicts directly in `api/main.py`.

```python
# Current pattern — structured detail dict
raise HTTPException(
    status_code=503,
    detail={
        "error": "anthropic_unavailable",
        "message": "ANTHROPIC_API_KEY is not configured. Set it in .env to enable agent endpoints.",
    },
)

raise HTTPException(
    status_code=404,
    detail={
        "error": "expert_not_found",
        "message": f"Expert '{expert_id}' not found. Use GET /agents for available experts.",
    },
)
```

### Recommended: Create `api/exceptions.py`

To reduce inline boilerplate and standardize error shapes, create custom
exception classes:

```python
# api/exceptions.py (recommended — does not exist yet)
from fastapi import HTTPException


class NotFoundError(HTTPException):
    def __init__(self, resource: str, resource_id: str | None = None) -> None:
        detail: dict = {"error": "not_found", "resource": resource}
        if resource_id:
            detail["id"] = resource_id
        detail["message"] = f"{resource} not found."
        super().__init__(status_code=404, detail=detail)


class ServiceUnavailableError(HTTPException):
    def __init__(self, service: str, message: str) -> None:
        super().__init__(
            status_code=503,
            detail={"error": f"{service}_unavailable", "message": message},
        )


class ForbiddenError(HTTPException):
    def __init__(self, message: str = "Insufficient permissions") -> None:
        super().__init__(
            status_code=403,
            detail={"error": "forbidden", "message": message},
        )
```

Usage after creating `api/exceptions.py`:

```python
# CORRECT — custom exception with structured detail
from api.exceptions import NotFoundError, ServiceUnavailableError

raise NotFoundError("bracket", bracket_id)
raise ServiceUnavailableError("anthropic", "ANTHROPIC_API_KEY is not configured.")

# WRONG — bare string detail
raise HTTPException(status_code=404, detail="Not found")

# WRONG — generic message without context
raise HTTPException(status_code=503, detail="Service unavailable")
```

---

## Error Response Shape

All error responses should follow a consistent JSON structure with an `error`
code (machine-readable) and a `message` (human-readable):

```json
// 404
{"error": "expert_not_found", "message": "Expert 'xyz' not found. Use GET /agents for available experts."}

// 503 — service unavailable
{"error": "anthropic_unavailable", "message": "ANTHROPIC_API_KEY is not configured."}

// 401
{"detail": "Invalid or expired token."}

// 400
{"detail": "No fields to update."}

// 503 — database unavailable
{"detail": "Database not configured."}
```

Note: The auth errors in `api/auth.py` and some simple errors in `api/main.py`
currently use bare string `detail`. When creating `api/exceptions.py`, migrate
these to structured dicts for consistency.

---

## SSE Error Payloads

SSE streaming endpoints (`/agents/{expert_id}/chat`) send error information
inline in the event stream using the `{"chunk": ..., "done": bool}` protocol.

```python
# Current pattern in api/main.py
async def event_generator():
    try:
        async for chunk in handle_chat(...):
            yield chunk
    except asyncio.CancelledError:
        logger.info("Client disconnected from SSE stream for expert %s", expert_id)
        return
    except Exception:
        logger.exception("Error in agent chat stream for expert %s", expert_id)
        error_payload = json.dumps({"chunk": "", "done": True, "error": "Internal error"})
        yield f"data: {error_payload}\n\n"
```

### SSE Error Rules

- Always set `"done": True` in error payloads so the client stops listening
- Never expose stack traces or internal error messages in SSE payloads
- Use `"error": "Internal error"` as the safe default message
- Log the full exception server-side with `logger.exception()`
- Handle `asyncio.CancelledError` separately — this is a normal disconnect, not an error

```python
# CORRECT — safe SSE error payload
error_payload = json.dumps({"chunk": "", "done": True, "error": "Internal error"})
yield f"data: {error_payload}\n\n"

# WRONG — exposes internal details in SSE
error_payload = json.dumps({"chunk": "", "done": True, "error": str(e)})
yield f"data: {error_payload}\n\n"

# WRONG — not setting done: True (client keeps listening)
error_payload = json.dumps({"error": "something went wrong"})
yield f"data: {error_payload}\n\n"
```

---

## Rules

### Always use structured detail dicts

```python
# CORRECT — structured dict with error code and message
raise HTTPException(
    status_code=503,
    detail={"error": "experts_unavailable", "message": "Expert analysts module is not available."},
)

# WRONG — bare string detail
raise HTTPException(status_code=503, detail="Experts not available")
```

### Never expose internal details

```python
# CORRECT — safe message
try:
    result = sb.table("user_brackets").insert(data).execute()
except Exception:
    logger.exception("Failed to create bracket")
    raise HTTPException(
        status_code=500,
        detail={"error": "internal_error", "message": "An unexpected error occurred."},
    )

# WRONG — exposes stack trace or DB error
except Exception as e:
    raise HTTPException(500, detail=str(e))  # leaks internals
```

### Check for empty results consistently

```python
# CORRECT — check result.data before indexing
result = sb.table("user_brackets").select("*").eq("id", bracket_id).eq("user_id", user_id).execute()
if not result.data:
    raise HTTPException(status_code=404, detail="Bracket not found.")
return result.data[0]

# WRONG — indexing without checking
return result.data[0]  # IndexError if empty
```

### Handle service unavailability with 503

```python
# CORRECT — 503 for missing infrastructure
sb = request.app.state.supabase
if not sb:
    raise HTTPException(status_code=503, detail="Database not configured.")

client = request.app.state.anthropic_client
if client is None:
    raise HTTPException(
        status_code=503,
        detail={"error": "anthropic_unavailable", "message": "ANTHROPIC_API_KEY is not configured."},
    )

# WRONG — 500 for missing config
if not sb:
    raise HTTPException(status_code=500, detail="Database error")
```

---

## Checklist

- [ ] Error `detail` is a dict with `error` and `message` keys (or migrating toward this)
- [ ] Never exposes stack traces, DB errors, or internal state
- [ ] Always checks `result.data` before indexing
- [ ] 503 for unavailable services (Supabase, Anthropic, expert module)
- [ ] SSE errors use `{"chunk": "", "done": true, "error": "..."}` format
- [ ] `asyncio.CancelledError` handled separately from other exceptions in SSE
- [ ] Full exceptions logged server-side with `logger.exception()`
- [ ] Consider creating `api/exceptions.py` for reusable exception classes
