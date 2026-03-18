---
description: Run security checks before committing new/modified Python or Dart code
alwaysApply: true
---

Before committing new or modified code, review for security issues:

**Python (api/, src/):**
- Never hardcode API keys, secrets, or credentials — use `pydantic-settings` + `.env`
- Validate all request inputs with Pydantic models — never trust raw request data
- Use `HTTPException` with structured `detail` dicts — never expose stack traces
- SSE endpoints must handle client disconnects gracefully (catch `asyncio.CancelledError`)
- Anthropic API key must come from environment, never from request bodies or query params
- CORS origins should be restricted in production — `["*"]` is dev-only

**Flutter/Dart (app/):**
- Never embed API keys or secrets in Dart code — use `--dart-define` or runtime config
- Sanitize user input before sending to API (chat messages, bracket submissions)
- Validate deep link / route parameters before use
- SSE connections must have timeout and retry logic — never leave streams open indefinitely
- Store no sensitive data in `SharedPreferences` — use `flutter_secure_storage` if needed

**Both:**
- Never commit `.env`, `*.pem`, `*.key`, or credential files
- Check that no secrets appear in git diff before staging
