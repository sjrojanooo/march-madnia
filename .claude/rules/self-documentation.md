---
description: After making changes, update co-located documentation
alwaysApply: true
---

After making changes, update documentation in the relevant scope:
- Pipeline or model changes → root `CLAUDE.md` (Data Coverage, Active Feature Set, Known Bugs)
- API endpoint changes → `api/` section of CLAUDE.md or inline docstrings
- Flutter app architecture → `app/` section of CLAUDE.md
- Error fixes and gotchas → Known Bugs Fixed section in CLAUDE.md
- Agent persona changes → relevant agent spec in `.claude/agents/`

Stay scoped to what you changed. Keep updates minimal and high-signal.

For substantial changes (new service, major refactors, multiple files), suggest
a dedicated audit via the `claude-md-refiner` agent.
