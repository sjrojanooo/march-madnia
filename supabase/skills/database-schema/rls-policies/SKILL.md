---
name: RLS Policies
description: This skill should be used when the user asks to "add RLS to a table", "create a row level security policy", "secure a table with RLS", "add a policy for user access", or "set up public read access on a table". It covers public-read vs user-scoped table patterns, service_role bypass policies, and performance-optimized auth checks.
version: 1.0.0
---

# RLS Policies

## Context

Every table in March Madness has RLS enabled. Tables fall into two categories:
**public-read** tables (reference data served to all users) and **user-scoped**
tables (personal data owned by individual users). The FastAPI backend uses
`service_role` to bypass RLS for system operations like seeding data.

### Table Classification

| Category | Tables | Access pattern |
|----------|--------|---------------|
| Public read | `teams`, `bracket_predictions`, `expert_picks`, `articles`, `article_embeddings` | Anyone can SELECT; only service role writes |
| User-scoped | `user_brackets`, `bracket_ratings`, `chat_history` | Users CRUD their own rows via `auth.uid() = user_id` |

## Rules

### 1. Every table must have RLS enabled

No exceptions. Add `ALTER TABLE ... ENABLE ROW LEVEL SECURITY;` immediately
after `CREATE TABLE`.

**CORRECT:**

```sql
CREATE TABLE user_brackets (
  id   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  -- ...
);

ALTER TABLE user_brackets ENABLE ROW LEVEL SECURITY;
```

**WRONG:**

```sql
CREATE TABLE user_brackets ( ... );
-- Missing RLS — table is open to all authenticated users via PostgREST
```

### 2. Public-read tables: allow SELECT for everyone

Reference data tables use a simple public-read policy. Only the backend
(service role) writes to these tables.

```sql
-- From 20260318100200_teams.sql
ALTER TABLE public.teams ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Teams are publicly readable"
  ON public.teams FOR SELECT
  USING (true);
```

### 3. User-scoped tables: use `auth.uid() = user_id`

User-owned tables restrict all operations to the row owner.

```sql
-- From 20260318100500_user_brackets.sql
CREATE POLICY "Users can read own brackets"
  ON public.user_brackets FOR SELECT
  USING (auth.uid() = user_id);

CREATE POLICY "Users can insert own brackets"
  ON public.user_brackets FOR INSERT
  WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can update own brackets"
  ON public.user_brackets FOR UPDATE
  USING (auth.uid() = user_id);

CREATE POLICY "Users can delete own brackets"
  ON public.user_brackets FOR DELETE
  USING (auth.uid() = user_id);
```

### 4. Use `(SELECT auth.uid())` for performance on large tables

Wrapping in `SELECT` forces PostgreSQL to cache the result once per statement
instead of evaluating per-row. Use this pattern on tables expected to grow
large (e.g., `chat_history`).

**CORRECT:**

```sql
CREATE POLICY "users can view own chat history"
  ON chat_history FOR SELECT
  TO authenticated
  USING (user_id = (SELECT auth.uid()));
```

**WRONG:**

```sql
-- Evaluates auth.uid() for every row — performance hit on large tables
USING (user_id = auth.uid());
```

### 5. Always include a `service_role` bypass policy on user-scoped tables

The backend needs to bypass RLS for system operations (seeding data, admin
actions). User-scoped tables need this policy. Public-read tables already
allow SELECT to everyone, so they only need a service role write policy
if the backend inserts data.

```sql
CREATE POLICY "service role full access"
  ON user_brackets FOR ALL
  TO service_role
  USING (true)
  WITH CHECK (true);
```

**WRONG:**

```sql
-- Missing service_role policy — backend writes will fail silently
```

### 6. Separate SELECT from INSERT/UPDATE/DELETE

Use specific policies per operation. Don't rely on a single `FOR ALL` unless
the same role has identical access for all operations.

```sql
-- Users can read their own brackets
CREATE POLICY "Users can read own brackets"
  ON public.user_brackets FOR SELECT
  USING (auth.uid() = user_id);

-- Users can insert their own brackets
CREATE POLICY "Users can insert own brackets"
  ON public.user_brackets FOR INSERT
  WITH CHECK (auth.uid() = user_id);
```

### 7. Use `WITH CHECK` for INSERT and UPDATE policies

`USING` filters rows for SELECT/UPDATE/DELETE. `WITH CHECK` validates new/modified
rows for INSERT/UPDATE.

**WRONG:**

```sql
-- Missing WITH CHECK — allows inserting rows the user can't read back
CREATE POLICY "users can insert"
  ON chat_history FOR INSERT
  TO authenticated
  USING (user_id = (SELECT auth.uid()));
```

**CORRECT:**

```sql
CREATE POLICY "users can insert"
  ON chat_history FOR INSERT
  TO authenticated
  WITH CHECK (user_id = (SELECT auth.uid()));
```
