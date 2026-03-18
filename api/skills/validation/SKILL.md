---
description: "Reference for Pydantic validation in the March Madness FastAPI backend — request/response models, field constraints, serialization patterns"
---

# Pydantic Validation & Schema Patterns

## Purpose

Guide the creation of Pydantic request/response models in the March Madness
Predictor backend. Follow this skill when adding schemas for new resources,
adding field validators, or ensuring alignment with the Flutter frontend.

---

## Base Class

All schemas in `api/models.py` inherit directly from `pydantic.BaseModel`:

```python
from pydantic import BaseModel, Field

class AgentChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)
    conversation_history: list[dict[str, str]] = Field(default_factory=list)
```

There is no custom `ORMBase` — `BaseModel` is used directly since March
Madness does not use SQLAlchemy ORM.

---

## Separate Create / Update / Response Schemas

Every resource that supports CRUD has three schema variants. Never reuse a
single model for multiple purposes.

```python
# CORRECT — three separate schemas (from api/models.py)
class UserBracketCreate(BaseModel):
    picks: dict[str, str]  # game_slot -> team_slug
    name: str = Field(default="My Bracket", max_length=100)

class UserBracketUpdate(BaseModel):
    picks: dict[str, str] | None = None
    name: str | None = Field(default=None, max_length=100)

class UserBracketResponse(BaseModel):
    id: str
    user_id: str
    season: int
    picks: dict[str, str]
    name: str
    created_at: str
    updated_at: str

# WRONG — single schema for everything
class UserBracket(BaseModel):
    id: str | None = None       # optional ID is a code smell
    picks: dict[str, str]
    name: str
    created_at: str | None = None
```

### Pattern Details

| Schema       | Purpose            | ID field | Optional fields   | Validators |
|--------------|--------------------|----------|-------------------|------------|
| `*Create`    | POST request body  | No       | Domain-specific   | Yes        |
| `*Update`    | PUT/PATCH body     | No       | All optional      | Rare       |
| `*Response`  | Response model     | Yes      | Domain-specific   | No         |

### Update Schema Convention

All fields in Update schemas are `Optional` (defaulting to `None`). Build the
update payload by checking for non-None values:

```python
# CORRECT — check each field (current pattern in api/main.py)
updates = {}
if body.picks is not None:
    updates["picks"] = body.picks
if body.name is not None:
    updates["name"] = body.name
if not updates:
    raise HTTPException(status_code=400, detail="No fields to update.")

# ALTERNATIVE — model_dump with exclude_none
updates = body.model_dump(exclude_none=True)
if not updates:
    raise HTTPException(status_code=400, detail="No fields to update.")
```

---

## Current Models in `api/models.py`

### Agent Models

```python
class AgentInfo(BaseModel):
    expert_id: str
    expert_name: str
    source: str
    style_summary: str

class AgentChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)
    conversation_history: list[dict[str, str]] = Field(default_factory=list)

class AgentRateBracketRequest(BaseModel):
    user_bracket: dict[str, str]  # game_slot -> team_slug

class BracketSuggestion(BaseModel):
    game_slot: str
    current_pick: str
    suggested_pick: str
    reasoning: str

class AgentRateBracketResponse(BaseModel):
    expert_id: str
    rating: int = Field(..., ge=1, le=10)
    overall_assessment: str
    suggestions: list[BracketSuggestion]
```

### User Bracket Models

```python
class UserBracketCreate(BaseModel):
    picks: dict[str, str]
    name: str = Field(default="My Bracket", max_length=100)

class UserBracketUpdate(BaseModel):
    picks: dict[str, str] | None = None
    name: str | None = Field(default=None, max_length=100)

class UserBracketResponse(BaseModel):
    id: str
    user_id: str
    season: int
    picks: dict[str, str]
    name: str
    created_at: str
    updated_at: str
```

### Chat History Model

```python
class ChatHistoryUpdate(BaseModel):
    messages: list[dict[str, str]]  # [{role: "user"|"assistant", content: "..."}]
```

---

## Field Types

### String IDs

March Madness uses `str` for all IDs (Supabase UUIDs come back as strings):

```python
# CORRECT — str for Supabase IDs
class UserBracketResponse(BaseModel):
    id: str
    user_id: str

# ALSO ACCEPTABLE — uuid.UUID if you want type validation on input
import uuid
class UserBracketResponse(BaseModel):
    id: uuid.UUID
```

### Constrained Numbers

Use `Field()` with `ge`/`le` for bounded numbers:

```python
# CORRECT — bounded rating
class AgentRateBracketResponse(BaseModel):
    rating: int = Field(..., ge=1, le=10)

# WRONG — no bounds
class AgentRateBracketResponse(BaseModel):
    rating: int  # could be -999 or 999
```

### Constrained Strings

Use `Field()` with `min_length`/`max_length`:

```python
# CORRECT — bounded string
class AgentChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)

# WRONG — no constraints
class AgentChatRequest(BaseModel):
    message: str
```

### Dict Fields

For bracket picks (game_slot -> team_slug), use `dict[str, str]`:

```python
class UserBracketCreate(BaseModel):
    picks: dict[str, str]  # game_slot -> team_slug
```

Consider adding a validator to ensure picks is not empty:

```python
from pydantic import field_validator

class UserBracketCreate(BaseModel):
    picks: dict[str, str]

    @field_validator("picks")
    @classmethod
    def picks_not_empty(cls, v: dict) -> dict:
        if not v:
            raise ValueError("picks must contain at least one entry")
        return v
```

### Optional Fields

Use `Type | None = None` syntax (not `Optional[Type]`):

```python
# CORRECT — union syntax
class UserBracketUpdate(BaseModel):
    picks: dict[str, str] | None = None
    name: str | None = Field(default=None, max_length=100)

# WRONG — old Optional syntax
from typing import Optional
class UserBracketUpdate(BaseModel):
    picks: Optional[dict[str, str]] = None
```

---

## Snake Case Convention

All schema field names use `snake_case`. The Flutter frontend maps these to
`camelCase` on its side. Never use camelCase in Python schemas:

```python
# CORRECT — snake_case
class AgentRateBracketResponse(BaseModel):
    expert_id: str
    overall_assessment: str

# WRONG — camelCase
class AgentRateBracketResponse(BaseModel):
    expertId: str
    overallAssessment: str
```

---

## Schema File Organization

All schemas live in a single file: `api/models.py`. Group related schemas
together with comments. If the file grows large, split into:

```
api/
    models/
        __init__.py          # re-exports all models
        agents.py            # AgentInfo, AgentChatRequest, etc.
        brackets.py          # UserBracketCreate/Update/Response
        chat.py              # ChatHistoryUpdate
```

---

## Checklist

- [ ] Inherits from `BaseModel`
- [ ] Separate `Create` / `Update` / `Response` schemas
- [ ] Update schema has all fields optional with `| None = None`
- [ ] `Field()` with constraints for strings (`min_length`/`max_length`) and numbers (`ge`/`le`)
- [ ] `snake_case` field names (never camelCase)
- [ ] `response_model=` set on every endpoint
- [ ] Dict fields documented with comments (e.g., `# game_slot -> team_slug`)
- [ ] Empty-check before database update (`if not updates: raise 400`)
