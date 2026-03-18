---
description: "Reference for Server-Sent Events (SSE) streaming in the March Madness backend — StreamingResponse, event protocol, CancelledError handling, error payloads"
---

# Server-Sent Events (SSE)

## Purpose

Guide the implementation of SSE streaming endpoints in the March Madness
Predictor backend. Follow this skill when building or modifying the agent
chat streaming endpoint or adding new real-time features.

---

## Current Implementation

March Madness uses raw `StreamingResponse` with manual SSE formatting
(not `EventSourceResponse`). The SSE protocol sends JSON payloads prefixed
with `data: ` and terminated with `\n\n`.

### Core Pattern (from `api/main.py`)

```python
from fastapi.responses import StreamingResponse

@app.post("/agents/{expert_id}/chat")
async def agent_chat(
    expert_id: str,
    body: AgentChatRequest,
    request: Request,
) -> StreamingResponse:
    client = _require_anthropic(request)
    bracket_context = get_bracket_context(
        request.app.state.bracket_data,
        request.app.state.expert_data,
    )

    async def event_generator():
        try:
            async for chunk in handle_chat(
                expert_id=expert_id,
                message=body.message,
                conversation_history=body.conversation_history,
                bracket_context=bracket_context,
                client=client,
            ):
                yield chunk
        except asyncio.CancelledError:
            logger.info("Client disconnected from SSE stream for expert %s", expert_id)
            return
        except Exception:
            logger.exception("Error in agent chat stream for expert %s", expert_id)
            error_payload = json.dumps({"chunk": "", "done": True, "error": "Internal error"})
            yield f"data: {error_payload}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")
```

---

## Event Protocol

Each SSE event is a JSON object sent as `data: {json}\n\n`:

```
data: {"chunk": "The", "done": false}\n\n
data: {"chunk": " Florida", "done": false}\n\n
data: {"chunk": " Gators", "done": false}\n\n
data: {"chunk": "", "done": true}\n\n
```

### Payload Shape

| Field | Type | Description |
|-------|------|-------------|
| `chunk` | `string` | Text fragment from the LLM response |
| `done` | `bool` | `true` on the final event (client should close connection) |
| `error` | `string` (optional) | Error message — only present on error events |

### Final Event

The last event always has `"done": true`. The client uses this signal to
stop listening and assemble the full response.

### Error Event

Error events set `"done": true` and include an `"error"` field:

```
data: {"chunk": "", "done": true, "error": "Internal error"}\n\n
```

---

## CancelledError Handling

When a client disconnects mid-stream, FastAPI raises `asyncio.CancelledError`.
This is a normal event, not an error — handle it gracefully:

```python
# CORRECT — catch CancelledError separately, log at INFO, return cleanly
try:
    async for chunk in handle_chat(...):
        yield chunk
except asyncio.CancelledError:
    logger.info("Client disconnected from SSE stream for expert %s", expert_id)
    return
except Exception:
    logger.exception("Error in agent chat stream")
    yield f"data: {json.dumps({'chunk': '', 'done': True, 'error': 'Internal error'})}\n\n"

# WRONG — not catching CancelledError (unhandled exception noise in logs)
async for chunk in handle_chat(...):
    yield chunk

# WRONG — treating disconnect as an error
except asyncio.CancelledError:
    logger.error("SSE stream cancelled!")  # Not an error — use info
```

---

## Rules

### Use `StreamingResponse` with `text/event-stream`

March Madness uses raw `StreamingResponse`, not `EventSourceResponse`. This is
because the Anthropic streaming API produces chunks that are manually formatted
into SSE events by the `handle_chat()` function.

```python
# CORRECT — current MM pattern
return StreamingResponse(event_generator(), media_type="text/event-stream")

# NOT USED in MM — EventSourceResponse is for new-style FastAPI SSE
from fastapi.sse import EventSourceResponse
```

If adding a new SSE endpoint that does not wrap an external streaming API,
consider using `EventSourceResponse` for automatic keep-alive and Pydantic
serialization.

### Always set `done: true` on the last event

```python
# CORRECT — client knows to stop
yield f"data: {json.dumps({'chunk': final_text, 'done': True})}\n\n"

# WRONG — no done signal (client waits indefinitely)
yield f"data: {json.dumps({'chunk': final_text})}\n\n"
```

### Never expose internal errors in SSE payloads

```python
# CORRECT — generic error message
error_payload = json.dumps({"chunk": "", "done": True, "error": "Internal error"})
yield f"data: {error_payload}\n\n"

# WRONG — leaks exception details
error_payload = json.dumps({"chunk": "", "done": True, "error": str(e)})
yield f"data: {error_payload}\n\n"
```

### Never block the event loop

```python
# WRONG — blocks the event loop
import time
time.sleep(1)

# CORRECT
await asyncio.sleep(1)
```

### Format SSE events correctly

Each event must be prefixed with `data: ` and terminated with `\n\n`:

```python
# CORRECT — proper SSE format
yield f"data: {json.dumps(payload)}\n\n"

# WRONG — missing data: prefix (not valid SSE)
yield f"{json.dumps(payload)}\n\n"

# WRONG — single newline (SSE requires double newline)
yield f"data: {json.dumps(payload)}\n"
```

---

## Adding a New SSE Endpoint

If adding a new streaming endpoint:

1. Define an `async def event_generator()` inner function
2. Wrap the generator with `try/except asyncio.CancelledError`
3. Use the `{"chunk": ..., "done": bool}` protocol for consistency
4. Return `StreamingResponse(event_generator(), media_type="text/event-stream")`
5. Validate inputs before starting the stream (auth, expert_id, etc.)

```python
@app.post("/agents/{expert_id}/new-stream")
async def new_stream_endpoint(
    expert_id: str,
    body: SomeRequest,
    request: Request,
) -> StreamingResponse:
    # Validate before streaming
    _validate_expert_id(expert_id)
    client = _require_anthropic(request)

    async def event_generator():
        try:
            async for chunk in some_async_generator(...):
                payload = json.dumps({"chunk": chunk, "done": False})
                yield f"data: {payload}\n\n"
            # Final event
            yield f"data: {json.dumps({'chunk': '', 'done': True})}\n\n"
        except asyncio.CancelledError:
            logger.info("Client disconnected")
            return
        except Exception:
            logger.exception("Stream error")
            yield f"data: {json.dumps({'chunk': '', 'done': True, 'error': 'Internal error'})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")
```

---

## Checklist

- [ ] Uses `StreamingResponse` with `media_type="text/event-stream"`
- [ ] Events formatted as `data: {json}\n\n`
- [ ] Payload follows `{"chunk": str, "done": bool}` protocol
- [ ] Final event has `"done": true`
- [ ] Error events include `"error"` field and `"done": true`
- [ ] `asyncio.CancelledError` caught and logged at INFO level
- [ ] Other exceptions caught, logged with `logger.exception()`, safe error yielded
- [ ] No internal error details exposed in SSE payloads
- [ ] Inputs validated before starting the stream (auth, expert_id, etc.)
- [ ] No blocking calls (`time.sleep`, synchronous I/O) in the generator
