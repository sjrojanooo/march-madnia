---
name: API Testing
description: "Use this skill when writing pytest tests for FastAPI endpoints, creating test fixtures, generating test JWTs, testing auth boundaries, or setting up async test infrastructure. Trigger phrases: 'write a test', 'add tests for this endpoint', 'test fixture', 'test JWT token', 'pytest setup', 'integration test', 'test auth'."
version: 1.0.0
---

# Testing Patterns

## Purpose

Establish testing patterns for the March Madness Predictor FastAPI backend.
The project currently has zero tests — this skill defines the conventions to
follow when adding tests.

---

## Test Runner

Always use `uv run pytest` from the project root:

```bash
# Run all tests
uv run pytest api/tests/

# Run a specific test file
uv run pytest api/tests/test_bracket.py

# Run a specific test
uv run pytest api/tests/test_bracket.py::test_get_bracket_returns_data

# Verbose output
uv run pytest -v

# Stop on first failure
uv run pytest -x
```

```bash
# WRONG — never use pip or bare pytest
pip install pytest && pytest
python -m pytest
```

---

## Test Structure

Tests live in `api/tests/`, one file per domain:

```
api/tests/
    __init__.py
    conftest.py              # Shared fixtures (client, env vars, test tokens)
    test_bracket.py          # /bracket endpoint tests
    test_experts.py          # /experts endpoint tests
    test_agents.py           # /agents/* endpoint tests
    test_user_brackets.py    # /user/brackets/* endpoint tests
    test_chat_history.py     # /user/chat-history/* endpoint tests
```

New test files go in `api/tests/` and are named `test_<resource>.py`.

---

## Fixtures — `api/tests/conftest.py`

### Environment Setup

Environment variables must be set **before** importing the app. This is
critical because `pydantic-settings` reads env vars at import time:

```python
import os
import pytest
from httpx import ASGITransport, AsyncClient

# Set env vars BEFORE importing the app
os.environ.setdefault("SUPABASE_URL", os.getenv("SUPABASE_URL", "http://localhost:54321"))
os.environ.setdefault("SUPABASE_ANON_KEY", os.getenv("SUPABASE_ANON_KEY", "dummy-anon-key"))
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", os.getenv("SUPABASE_SERVICE_ROLE_KEY", "dummy-service-role-key"))
os.environ.setdefault("JWT_SECRET", os.getenv("JWT_SECRET", "super-secret-jwt-token-with-at-least-32-characters-long"))
os.environ.setdefault("ANTHROPIC_API_KEY", os.getenv("ANTHROPIC_API_KEY", ""))

from api.main import app  # noqa: E402 — must come after env setup
```

### AsyncClient Fixture

```python
@pytest.fixture
async def client() -> AsyncClient:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac
```

### anyio Backend Fixture

```python
@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"
```

### Test JWT Helper

Use `python-jose` (the same library used in `api/auth.py`) to create test tokens:

```python
import uuid
from datetime import datetime, timezone, timedelta
from jose import jwt

JWT_SECRET = "super-secret-jwt-token-with-at-least-32-characters-long"

def make_test_token(user_id: str | None = None) -> str:
    """Create a valid test JWT matching Supabase format."""
    payload = {
        "sub": user_id or str(uuid.uuid4()),
        "aud": "authenticated",
        "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm="HS256")
```

Note: The `aud: "authenticated"` claim is required — `api/auth.py` validates
the audience.

---

## Writing Tests

### Arrange-Act-Assert Pattern

Every test follows Arrange-Act-Assert:

```python
@pytest.mark.asyncio
async def test_get_bracket_returns_data(client: AsyncClient) -> None:
    # Arrange — (nothing to set up, testing public endpoint)

    # Act
    response = await client.get("/bracket")

    # Assert
    assert response.status_code == 200
    assert isinstance(response.json(), dict)
```

### Test Naming Convention

`test_<resource>_<action>_<status>_<condition>`:

```python
# CORRECT — descriptive names
async def test_get_bracket_returns_data(client: AsyncClient) -> None: ...
async def test_list_agents_returns_list(client: AsyncClient) -> None: ...
async def test_list_user_brackets_401_no_token(client: AsyncClient) -> None: ...
async def test_create_user_bracket_401_invalid_token(client: AsyncClient) -> None: ...
async def test_create_user_bracket_503_no_database(client: AsyncClient) -> None: ...

# WRONG — vague names
async def test_1(client): ...
async def test_brackets(client): ...
```

### Async Test Decorator

All tests must be marked with `@pytest.mark.asyncio`:

```python
# CORRECT
@pytest.mark.asyncio
async def test_get_bracket(client: AsyncClient) -> None:
    response = await client.get("/bracket")
    assert response.status_code == 200

# WRONG — missing marker
async def test_get_bracket(client: AsyncClient) -> None:
    response = await client.get("/bracket")  # will not run as async
```

### Type Hints on Tests

Always type-hint the `client` parameter and return `None`:

```python
# CORRECT
async def test_example(client: AsyncClient) -> None: ...

# WRONG — missing type hints
async def test_example(client): ...
```

---

## Example Tests

### Public Endpoints (no auth required)

```python
"""Bracket endpoint tests."""
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_get_bracket_returns_200(client: AsyncClient) -> None:
    """Public bracket endpoint returns data."""
    response = await client.get("/bracket")
    assert response.status_code == 200
    assert isinstance(response.json(), dict)


@pytest.mark.asyncio
async def test_get_experts_returns_200(client: AsyncClient) -> None:
    """Public experts endpoint returns data."""
    response = await client.get("/experts")
    assert response.status_code == 200
```

### Agent Endpoints

```python
"""Agent endpoint tests."""
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_list_agents_returns_list(client: AsyncClient) -> None:
    """GET /agents returns a list of expert agents."""
    response = await client.get("/agents")
    # May return 200 (list) or 503 (experts module not loaded)
    assert response.status_code in (200, 503)
    if response.status_code == 200:
        data = response.json()
        assert isinstance(data, list)
        if data:
            assert "expert_id" in data[0]
            assert "expert_name" in data[0]
```

### Auth-Required Endpoints

```python
"""User bracket endpoint tests."""
import pytest
from httpx import AsyncClient
from api.tests.conftest import make_test_token


@pytest.mark.asyncio
async def test_list_user_brackets_401_no_token(client: AsyncClient) -> None:
    """Unauthenticated request returns 401."""
    response = await client.get("/user/brackets")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_list_user_brackets_401_invalid_token(client: AsyncClient) -> None:
    """Invalid JWT returns 401."""
    response = await client.get(
        "/user/brackets",
        headers={"Authorization": "Bearer not.a.valid.jwt"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_create_user_bracket_with_valid_token(client: AsyncClient) -> None:
    """Creating a bracket with valid auth succeeds or returns 503 (no DB)."""
    token = make_test_token()
    response = await client.post(
        "/user/brackets",
        json={"picks": {"R1G1": "gonzaga"}, "name": "Test Bracket"},
        headers={"Authorization": f"Bearer {token}"},
    )
    # 201 if Supabase is running, 503 if not configured
    assert response.status_code in (201, 503)


@pytest.mark.asyncio
async def test_update_user_bracket_400_empty_body(client: AsyncClient) -> None:
    """Update with no fields returns 400."""
    token = make_test_token()
    response = await client.put(
        "/user/brackets/some-bracket-id",
        json={},
        headers={"Authorization": f"Bearer {token}"},
    )
    # 400 (no fields) or 503 (no DB) — both are acceptable
    assert response.status_code in (400, 503)
```

---

## Integration Tests — Real Supabase When Available

Tests should run against a real local Supabase instance when available
(`supabase start`). When Supabase is not running, tests should still pass
by asserting 503 for database-dependent operations:

```python
# CORRECT — handles both DB-available and DB-unavailable states
@pytest.mark.asyncio
async def test_list_brackets_with_auth(client: AsyncClient) -> None:
    token = make_test_token()
    response = await client.get(
        "/user/brackets",
        headers={"Authorization": f"Bearer {token}"},
    )
    if response.status_code == 200:
        assert isinstance(response.json(), list)
    else:
        assert response.status_code == 503

# WRONG — test only passes when Supabase is running
@pytest.mark.asyncio
async def test_list_brackets(client: AsyncClient) -> None:
    response = await client.get("/user/brackets", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200  # fails when DB is down
```

---

## Response Assertions

```python
# Assert status code
assert response.status_code == 200
assert response.status_code == 201
assert response.status_code == 204

# Assert JSON body
data = response.json()
assert isinstance(data, dict)
assert "picks" in data

# Assert list response
data = response.json()
assert isinstance(data, list)

# Assert error shape (structured detail)
assert response.status_code == 503
detail = response.json()["detail"]
assert detail["error"] == "anthropic_unavailable"

# Assert error shape (bare string detail)
assert response.status_code == 401
assert response.json()["detail"] == "Invalid or expired token."
```

---

## Adding a New Test File

1. Create `api/tests/test_<resource>.py`
2. Import `pytest` and `AsyncClient`
3. Use the `client` fixture from conftest
4. Start with auth boundary tests (401 for missing/invalid tokens)
5. Add public endpoint tests (200 for unauthenticated reads)
6. Add happy-path tests that handle 503 gracefully

```python
"""
Chat history endpoint tests.
"""
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_get_chat_history_401_no_token(client: AsyncClient) -> None:
    response = await client.get("/user/chat-history/analyst-jay")
    assert response.status_code == 401
```

---

## Checklist

- [ ] Test file in `api/tests/test_<resource>.py`
- [ ] `@pytest.mark.asyncio` on every async test
- [ ] Uses `client: AsyncClient` fixture (not `TestClient`)
- [ ] Type hints on all parameters and return `None`
- [ ] Follows Arrange-Act-Assert structure
- [ ] Tests auth boundaries (401 for missing/invalid tokens)
- [ ] Handles DB-unavailable gracefully (asserts 503 as alternative)
- [ ] Uses `make_test_token()` with `jose.jwt` for authenticated tests
- [ ] Token includes `aud: "authenticated"` claim
- [ ] Descriptive test names: `test_<resource>_<action>_<status>_<condition>`
- [ ] Run with `uv run pytest` (never bare `pytest`)
