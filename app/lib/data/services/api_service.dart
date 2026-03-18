import 'dart:convert';

import 'package:http/http.dart' as http;
import 'package:march_madness/core/models/agent_message.dart';
import 'package:march_madness/data/services/sse_service.dart';

class ApiService {
  final String baseUrl;
  final http.Client _client;

  ApiService({required this.baseUrl})
      : _client = http.Client();

  Uri _uri(String path) =>
      Uri.parse('$baseUrl$path');

  Future<Map<String, dynamic>> getBracket() async {
    final response = await _client.get(
      _uri('/bracket'),
    );
    _checkResponse(response);
    return jsonDecode(response.body)
        as Map<String, dynamic>;
  }

  Future<Map<String, dynamic>> getExperts() async {
    final response = await _client.get(
      _uri('/experts'),
    );
    _checkResponse(response);
    return jsonDecode(response.body)
        as Map<String, dynamic>;
  }

  Future<List<dynamic>> getAgents() async {
    final response = await _client.get(
      _uri('/agents'),
    );
    _checkResponse(response);
    return jsonDecode(response.body)
        as List<dynamic>;
  }

  Stream<String> chatWithAgent(
    String expertId,
    String message,
    List<AgentMessage> history,
  ) {
    return SseService.connect(
      uri: _uri('/agents/$expertId/chat'),
      body: {
        'message': message,
        'history': history
            .map((m) => m.toJson())
            .toList(),
      },
    );
  }

  Future<Map<String, dynamic>> rateBracket(
    String expertId,
    Map<String, String> bracket,
  ) async {
    final response = await _client.post(
      _uri('/agents/$expertId/rate'),
      headers: {
        'Content-Type': 'application/json',
      },
      body: jsonEncode({'bracket': bracket}),
    );
    _checkResponse(response);
    return jsonDecode(response.body)
        as Map<String, dynamic>;
  }

  void _checkResponse(http.Response response) {
    if (response.statusCode < 200 ||
        response.statusCode >= 300) {
      throw Exception(
        'API error ${response.statusCode}: '
        '${response.body}',
      );
    }
  }
}
