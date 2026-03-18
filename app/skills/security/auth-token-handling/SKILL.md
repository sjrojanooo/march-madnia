---
description: Supabase auth token lifecycle — session access, token passing, sign-out cleanup, PKCE flow
globs: ["**/*.dart"]
---

# Auth Token Handling

## Context

March Madness uses Supabase as the sole auth provider. Tokens are ephemeral,
managed entirely by the Supabase SDK, and never stored manually. The app uses
PKCE flow for web OAuth. Token access is centralized through `SupabaseService`.

## Rules

### 1. Access tokens via SupabaseService

Tokens are exposed through `SupabaseService.accessToken`, which reads from
`Supabase.instance.client.auth.currentSession`. Never cache, persist, or copy
tokens elsewhere.

See: `app/lib/data/services/supabase_service.dart`

**CORRECT:**

```dart
final supaService = context.read<SupabaseService>();
final token = supaService.accessToken;
if (token == null) return; // not authenticated
```

**WRONG:**

```dart
// Never store tokens in state or SharedPreferences
String? _savedToken;
void onLogin() {
  _savedToken = Supabase.instance.client.auth.currentSession?.accessToken; // stale token risk
}
```

### 2. ApiService does not pass auth tokens yet (known gap)

`ApiService` currently makes unauthenticated requests — no `Authorization`
header is attached. This is a known deficiency. When adding authenticated
endpoints, pass the token from `SupabaseService.accessToken` as a parameter
to the service method, not by reaching into Supabase directly.

See: `app/lib/data/services/api_service.dart`

**Future pattern (not yet implemented):**

```dart
Future<Map<String, dynamic>> getProtectedData(String accessToken) async {
  final response = await _client.get(
    _uri('/protected'),
    headers: {
      'Content-Type': 'application/json',
      'Authorization': 'Bearer $accessToken',
    },
  );
  _checkResponse(response);
  return jsonDecode(response.body) as Map<String, dynamic>;
}
```

**WRONG:**

```dart
// Don't reach into Supabase from inside ApiService
Future<Map<String, dynamic>> getProtectedData() async {
  final token = Supabase.instance.client.auth.currentSession!.accessToken;
  // ...
}
```

### 3. Sign-out must clear all session state

There is no `OrgSession` in March Madness. On sign-out, call
`SupabaseService.signOut()` which delegates to `_client?.auth.signOut()`.
If any cached data exists (e.g., `BracketRepository._cache`), clear it
before signing out to prevent stale data from surviving across sessions.

**CORRECT:**

```dart
Future<void> _signOut(BuildContext context) async {
  context.read<BracketRepository>().clearCache();
  await context.read<SupabaseService>().signOut();
  if (mounted) context.go('/');
}
```

**WRONG:**

```dart
Future<void> _signOut(BuildContext context) async {
  await context.read<SupabaseService>().signOut();
  // BracketRepository still holds previous user's cached data!
  context.go('/');
}
```

### 4. PKCE flow is configured at initialization

See: `app/lib/main.dart` and `app/lib/core/config/app_config.dart`

Supabase is initialized with the URL and anon key from dart-defines:

```dart
await Supabase.initialize(
  url: AppConfig.supabaseUrl,
  anonKey: AppConfig.supabaseAnonKey,
  authOptions: const FlutterAuthClientOptions(
    authFlowType: AuthFlowType.pkce,
  ),
);
```

Never change the auth flow type. PKCE prevents authorization code interception
on web.

### 5. Handle stale/expired sessions

Always check for null before using tokens — sessions can expire between
navigations.

**CORRECT:**

```dart
final supaService = context.read<SupabaseService>();
if (!supaService.isLoggedIn) {
  if (mounted) context.go('/login');
  return;
}
final token = supaService.accessToken!;
```

**WRONG:**

```dart
// Assuming session exists because user was logged in earlier
final token = context.read<SupabaseService>().accessToken!;
```
