---
description: Schema migrations — naming convention, idempotent patterns, timestamptz, reversibility
globs: ["supabase/migrations/**/*.sql"]
---

# Migrations

## Context

Migrations live in `supabase/migrations/` and follow the Supabase CLI naming
convention. They are applied in order by timestamp. Each migration should be
idempotent where possible, always use `timestamptz`, and avoid destructive
changes to existing data.

## Rules

### 1. Naming convention: `YYYYMMDDHHMMSS_<verb>_<subject>.sql`

Use a descriptive verb and subject. The timestamp ensures ordering.

**Examples from this codebase:**

```
20260318100100_extensions.sql
20260318100200_teams.sql
20260318100300_bracket_predictions.sql
20260318100400_expert_picks.sql
20260318100500_user_brackets.sql
20260318100600_bracket_ratings.sql
20260318100700_articles_and_embeddings.sql
20260318100800_chat_history.sql
```

**WRONG:**

```
001_create_tables.sql          -- no timestamp
20260318_stuff.sql             -- vague name, incomplete timestamp
```

### 2. Use `timestamptz` — never `timestamp`

All timestamp columns must use `timestamptz` (timestamp with time zone).

**CORRECT:**

```sql
created_at timestamptz NOT NULL DEFAULT now(),
updated_at timestamptz NOT NULL DEFAULT now()
```

**WRONG:**

```sql
created_at timestamp NOT NULL DEFAULT now()  -- loses timezone info
```

### 3. Use `gen_random_uuid()` for primary keys

Tables with UUID primary keys should use PostgreSQL-generated UUIDs.
Note: some tables (e.g., `teams`) use composite natural keys instead —
that is fine when the domain calls for it.

```sql
id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
```

**WRONG:**

```sql
id serial PRIMARY KEY,         -- sequential, predictable
id uuid PRIMARY KEY,           -- no default — app must generate
```

### 4. Use `IF NOT EXISTS` / `IF EXISTS` for idempotency

Extensions, functions, and indexes should be idempotent so migrations can be
safely re-run during development.

```sql
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE INDEX IF NOT EXISTS idx_user_brackets_user_id ON user_brackets(user_id);
DROP INDEX IF EXISTS idx_old_name;
```

### 5. Start each migration with a description comment

```sql
-- Description: User brackets for saving tournament picks.
```

### 6. Never drop columns or tables with data in production

For schema changes:
- Add new columns as nullable first
- Backfill data
- Then add constraints in a subsequent migration
- Never `DROP TABLE` unless it's truly empty

**WRONG:**

```sql
ALTER TABLE teams DROP COLUMN conference;  -- data loss
```

**CORRECT:**

```sql
-- Migration 1: add new column
ALTER TABLE teams ADD COLUMN conf_abbrev text;

-- Migration 2: backfill
UPDATE teams SET conf_abbrev = conference WHERE conference IS NOT NULL;

-- Migration 3: drop old column (after verifying backfill)
ALTER TABLE teams DROP COLUMN conference;
```

### 7. Include RLS and policies in the same migration as the table

Don't create a table in one migration and add RLS in another — the table is
exposed between migrations.

```sql
CREATE TABLE my_table ( ... );
ALTER TABLE my_table ENABLE ROW LEVEL SECURITY;
CREATE POLICY "..." ON my_table ...;
```
