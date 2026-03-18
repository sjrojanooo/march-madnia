---
description: Error handling — typed exceptions, catch-rethrow pattern, dart:developer logging, HTTP status mapping
globs: ["**/*.dart"]
---

# Error Handling

## Context

March Madness currently throws generic `Exception` from `ApiService` with raw
response bodies embedded — this is a known deficiency. The recommended pattern
is typed exception classes per service, `dart:developer` for logging, and
user-safe error messages. Raw error details should never be shown to users.

## Rules

### 1. Use typed exception classes (not yet implemented — current gap)

`ApiService._checkResponse` currently throws generic `Exception` with the raw
response body. This should be replaced with a typed `ApiException` class.

See: `app/lib/data/services/api_service.dart` lines 76-84

**Current code (deficiency):**

```dart
void _checkResponse(http.Response response) {
  if (response.statusCode < 200 || response.statusCode >= 300) {
    throw Exception(
      'API error ${response.statusCode}: ${response.body}',  // raw body exposed
    );
  }
}
```

**Recommended replacement:**

```dart
class ApiException implements Exception {
  ApiException(this.message, {this.statusCode});
  final String message;
  final int? statusCode;

  @override
  String toString() => 'ApiException: $message';
}

void _checkResponse(http.Response response) {
  if (response.statusCode < 200 || response.statusCode >= 300) {
    throw ApiException(
      'Request failed. Please try again.',
      statusCode: response.statusCode,
    );
  }
}
```

For domain-specific services, create dedicated exception classes:

```dart
class BracketServiceException implements Exception {
  BracketServiceException(this.message, {this.statusCode});
  final String message;
  final int? statusCode;

  @override
  String toString() => 'BracketServiceException: $message';
}
```

**WRONG:**

```dart
// Generic exceptions lose context and type information
throw Exception('Something went wrong');

// String exceptions are untyped and uncatchable by type
throw 'Failed to load bracket';
```

### 2. Catch-rethrow with safe messages

Services should catch HTTP errors and rethrow with user-safe messages. The raw
`response.body` should be logged but never exposed.

**CORRECT:**

```dart
Future<BracketData> getBracket() async {
  final response = await _client.get(_uri('/bracket'));
  if (response.statusCode == 200) {
    return _parseBracketData(jsonDecode(response.body));
  }
  throw ApiException(
    'Failed to load bracket data.',
    statusCode: response.statusCode,
  );
}
```

**WRONG:**

```dart
if (response.statusCode != 200) {
  // Exposes internal details to caller/UI
  throw Exception('${response.statusCode}: ${response.body}');
}
```

### 3. Use dart:developer for logging

Log errors with `dart:developer` `log()`, not `print()`. Include the error,
stack trace, and a descriptive name.

**CORRECT:**

```dart
import 'dart:developer';

try {
  final bracket = await repo.getBracket();
} catch (e, stack) {
  log('Failed to load bracket', error: e, stackTrace: stack, name: 'BracketScreen');
}
```

**WRONG:**

```dart
// print() is stripped in release mode and lacks structure
print('Error: $e');

// debugPrint is for debug output, not error logging
debugPrint('Failed: ${e.toString()}');
```

### 4. Widget error state pattern

Widgets should catch service exceptions and render user-safe error messages.
Use state enums (see state-management skill) for clean error rendering.

**CORRECT:**

```dart
Future<void> _loadData() async {
  setState(() => _state = LoadState.loading);
  try {
    _data = await context.read<BracketRepository>().getBracket();
    setState(() => _state = LoadState.loaded);
  } on ApiException catch (e) {
    setState(() {
      _state = LoadState.error;
      _errorMessage = e.message;
    });
  } catch (e, stack) {
    log('Unexpected error', error: e, stackTrace: stack, name: 'BracketScreen');
    setState(() {
      _state = LoadState.error;
      _errorMessage = 'An unexpected error occurred. Please try again.';
    });
  }
}
```

### 5. UI error rendering

Errors display as banners or inline messages, never as raw exception strings.

**CORRECT:**

```dart
if (_state == LoadState.error) ...[
  Container(
    padding: const EdgeInsets.all(16),
    color: Colors.red.shade900,
    child: Text(_errorMessage ?? 'Something went wrong.'),
  ),
  const SizedBox(height: 24),
],
```

**WRONG:**

```dart
// Showing raw exception to user
if (hasError) Text('Error: ${exception.toString()}')
```

### 6. Never swallow exceptions silently

Always either handle the error (set state + log) or rethrow it. Empty catch
blocks hide bugs.

**WRONG:**

```dart
try {
  await repo.getBracket();
} catch (_) {
  // Silently swallowed — user sees nothing, bug is hidden
}
```
