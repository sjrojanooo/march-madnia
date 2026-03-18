---
name: State Management
description: This skill should be used when the user asks to "add a new provider", "register a repository in MultiProvider", "use context.read or context.watch", "add state enums for loading states", or "implement repository caching". It covers Provider-based state management including MultiProvider setup, context.read/watch patterns, state enums, auth state isolation, and repository caching.
version: 1.0.0
---

# State Management

## Context

March Madness uses the `provider` package with `MultiProvider` at the app root.
Services and repositories are injected via `Provider<T>` and accessed in
widgets with `context.read<T>()` (one-time access) or `context.watch<T>()`
(reactive rebuild). This is distinct from singleton ChangeNotifier patterns —
do not introduce singletons or `ListenableBuilder`.

## Rules

### 1. MultiProvider at the app root

All services and repositories are registered in `main.dart` via `MultiProvider`.
Widgets access them through `context.read<T>()`.

See: `app/lib/main.dart`

```dart
void main() {
  final apiService = ApiService(baseUrl: AppConfig.apiBaseUrl);
  runApp(
    MultiProvider(
      providers: [
        Provider<ApiService>.value(value: apiService),
        Provider<BracketRepository>(
          create: (_) => BracketRepository(apiService),
        ),
        Provider<ExpertRepository>(
          create: (_) => ExpertRepository(apiService),
        ),
        Provider<AgentRepository>(
          create: (_) => AgentRepository(apiService),
        ),
      ],
      child: const MarchMadnessApp(),
    ),
  );
}
```

**WRONG — using singletons:**

```dart
// Don't use singleton pattern; use Provider injection
class BracketRepository {
  static final BracketRepository _instance = BracketRepository._();
  factory BracketRepository() => _instance;
  BracketRepository._();
}
```

### 2. Use context.read for one-time access, context.watch for reactive

Use `context.read<T>()` in `initState`, callbacks, and async methods where
you need the value once. Use `context.watch<T>()` in `build` methods when the
widget should rebuild on changes (only works with `ChangeNotifierProvider`).

See: `app/lib/features/bracket/bracket_screen.dart`

**CORRECT:**

```dart
@override
void didChangeDependencies() {
  super.didChangeDependencies();
  _future = context.read<BracketRepository>().getBracket();
}
```

See: `app/lib/features/agents/agent_chat_screen.dart`

```dart
final repo = context.read<AgentRepository>();
```

**WRONG:**

```dart
// Don't access providers outside the widget tree
final repo = BracketRepository();

// Don't use ListenableBuilder with Provider-managed objects
ListenableBuilder(
  listenable: someNotifier,
  builder: (context, _) => ...,
)
```

### 3. Use state enums over boolean flags

When a widget or notifier needs to track loading/error/success states, use an
enum with exhaustive switch. Boolean flags don't scale and create impossible
states (e.g., `isLoading && hasError` both true).

**CORRECT:**

```dart
enum BracketLoadState { idle, loading, loaded, error }

// In widget or notifier:
BracketLoadState _state = BracketLoadState.idle;

Widget build(BuildContext context) {
  return switch (_state) {
    BracketLoadState.idle => const SizedBox.shrink(),
    BracketLoadState.loading => const CircularProgressIndicator(),
    BracketLoadState.loaded => _BracketContent(data: _data!),
    BracketLoadState.error => _ErrorView(message: _errorMessage),
  };
}
```

**WRONG:**

```dart
// Boolean flags don't scale and allow impossible states
bool isLoading = false;
bool hasError = false;
bool isSuccess = false;
```

### 4. Auth state is isolated in SupabaseService

The app does not manage auth state in its own notifiers or providers. Auth state
lives in `SupabaseService`, which wraps the Supabase SDK. The router reads it
directly.

See: `app/lib/data/services/supabase_service.dart`

```dart
bool get isLoggedIn => currentUser != null;
String? get accessToken => _client?.auth.currentSession?.accessToken;
```

### 5. Repository caching pattern

Repositories own their cache. `BracketRepository` caches the parsed bracket
data and exposes a `clearCache()` method. Follow this pattern for new
repositories.

See: `app/lib/data/repositories/bracket_repository.dart`

```dart
class BracketRepository {
  final ApiService _api;
  BracketData? _cache;

  BracketRepository(this._api);

  Future<BracketData> getBracket({bool forceRefresh = false}) async {
    if (_cache != null && !forceRefresh) return _cache!;
    final data = await _api.getBracket();
    _cache = _parseBracketData(data);
    return _cache!;
  }

  void clearCache() => _cache = null;
}
```

### 6. Adding new providers

When adding a new service or repository:
1. Create the class in `app/lib/data/services/` or `app/lib/data/repositories/`
2. Register it in the `MultiProvider` in `app/lib/main.dart`
3. Access it via `context.read<T>()` in widgets

**CORRECT:**

```dart
// In main.dart providers list:
Provider<NewRepository>(
  create: (_) => NewRepository(apiService),
),

// In widget:
final repo = context.read<NewRepository>();
```

**WRONG:**

```dart
// Don't create instances directly in widgets
final repo = NewRepository(ApiService(baseUrl: AppConfig.apiBaseUrl));
```
