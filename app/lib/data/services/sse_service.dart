import 'dart:async';
import 'dart:convert';

import 'package:http/http.dart' as http;

class SseService {
  static Stream<String> connect({
    required Uri uri,
    required Map<String, dynamic> body,
    String? token,
    Duration timeout = const Duration(seconds: 60),
  }) async* {
    final client = http.Client();
    try {
      final request = http.Request('POST', uri)
        ..headers['Content-Type'] = 'application/json'
        ..headers['Accept'] = 'text/event-stream'
        ..body = jsonEncode(body);
      if (token != null) {
        request.headers['Authorization'] = 'Bearer $token';
      }

      final response = await client
          .send(request)
          .timeout(timeout);

      if (response.statusCode != 200) {
        throw Exception(
          'SSE connection failed: '
          '${response.statusCode}',
        );
      }

      var buffer = '';
      await for (final chunk
          in response.stream
              .transform(utf8.decoder)
              .timeout(timeout)) {
        buffer += chunk;
        final lines = buffer.split('\n');
        // Keep the last (possibly incomplete) line
        buffer = lines.removeLast();

        for (final line in lines) {
          final trimmed = line.trim();
          if (trimmed.isEmpty) continue;
          if (!trimmed.startsWith('data:')) {
            continue;
          }

          final payload =
              trimmed.substring('data:'.length).trim();
          if (payload.isEmpty) continue;

          try {
            final json =
                jsonDecode(payload) as Map<String, dynamic>;
            final done = json['done'] as bool? ?? false;
            if (done) return;
            final text = json['chunk'] as String? ?? '';
            if (text.isNotEmpty) {
              yield text;
            }
          } on FormatException {
            // Not valid JSON — skip
          }
        }
      }
    } on TimeoutException {
      // Stream timed out — close gracefully
    } finally {
      client.close();
    }
  }
}
