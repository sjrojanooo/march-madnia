---
name: API Security
description: This skill should be used when the user asks to "add auth headers to API requests", "fix the raw error body exposure", "inject an http.Client for testing", "enforce HTTPS in production", or "map HTTP status codes to user messages". It covers API security patterns including Bearer token headers, HTTPS enforcement, safe error messages, and http.Client injection for testability.
version: 1.0.0
---

# API Security

## Context

API calls go through `ApiService` which wraps an `http.Client`. The backend URL
comes from `AppConfig.apiBaseUrl` via dart-defines. Currently, `ApiService`
exposes raw response bodies in exceptions — this is a known violation flagged
below.

## Rules

### 1. Attach Bearer token for authenticated endpoints

`ApiService` does not currently attach auth headers (known gap). When adding
authenticated endpoints, pass the token as a method parameter and include it
in the request headers.

See: `app/lib/data/services/api_service.dart`

**CORRECT (future pattern):**

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
// Missing auth header — request will be rejected
final response = await _client.get(_uri('/protected'), headers: {
  'Content-Type': 'application/json',
});
```

### 2. Use http.Client injection for testability

`ApiService` already accepts `baseUrl` via constructor but creates its own
`http.Client` internally. For testability, accept an optional `http.Client`.

**CORRECT:**

```dart
class ApiService {
  ApiService({required this.baseUrl, http.Client? client})
      : _client = client ?? http.Client();

  final String baseUrl;
  final http.Client _client;
}
```

**WRONG:**

```dart
class ApiService {
  // Hardcoded client — can't mock in tests
  Future<void> fetch() async {
    final response = await http.get(Uri.parse(url));
  }
}
```

### 3. Never expose raw response bodies to users (CURRENT VIOLATION)

`ApiService._checkResponse` currently throws `Exception` with the raw
`response.body` embedded. This may contain stack traces, SQL errors, or
internal details.

See: `app/lib/data/services/api_service.dart` lines 76-84

**Current code (violation):**

```dart
void _checkResponse(http.Response response) {
  if (response.statusCode < 200 || response.statusCode >= 300) {
    throw Exception(
      'API error ${response.statusCode}: ${response.body}',  // VIOLATION
    );
  }
}
```

**Should be:**

```dart
void _checkResponse(http.Response response) {
  if (response.statusCode < 200 || response.statusCode >= 300) {
    throw ApiException(
      'Request failed. Please try again.',
      statusCode: response.statusCode,
    );
  }
}
```

### 4. HTTPS in production

The backend URL comes from dart-defines. In production, this must be HTTPS.
The default `http://localhost:8000` is for local development only.

See: `app/lib/core/config/app_config.dart`

```dart
static const String apiBaseUrl = String.fromEnvironment(
  'API_BASE_URL',
  defaultValue: 'http://localhost:8000',
);
```

Never hardcode a production HTTP URL. CI/CD sets `API_BASE_URL` to the HTTPS
endpoint.

### 5. Map HTTP status codes to user-safe messages

Translate status codes to actionable messages rather than showing raw codes.

**CORRECT:**

```dart
String _userMessage(int statusCode) => switch (statusCode) {
  401 => 'Your session has expired. Please sign in again.',
  403 => 'You do not have permission to perform this action.',
  404 => 'The requested resource was not found.',
  409 => 'This conflicts with an existing record.',
  422 => 'Please check your input and try again.',
  _ => 'Something went wrong. Please try again later.',
};
```

**WRONG:**

```dart
ScaffoldMessenger.of(context).showSnackBar(
  SnackBar(content: Text('Error ${response.statusCode}: ${response.body}')),
);
```
