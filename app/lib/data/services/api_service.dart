import 'dart:convert';
import 'dart:developer' as developer;

import 'package:http/http.dart' as http;
import 'package:march_madness/core/models/agent_message.dart';
import 'package:march_madness/data/services/api_exception.dart';
import 'package:march_madness/data/services/sse_service.dart';

class ApiService {
  final String baseUrl;
  final http.Client _client;

  ApiService({required this.baseUrl})
      : _client = http.Client();

  Uri _uri(String path) =>
      Uri.parse('$baseUrl$path');

  Map<String, String> _headers({String? token}) {
    final headers = <String, String>{
      'Content-Type': 'application/json',
    };
    if (token != null) {
      headers['Authorization'] = 'Bearer $token';
    }
    return headers;
  }

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
    List<AgentMessage> history, {
    String? token,
  }) {
    return SseService.connect(
      uri: _uri('/agents/$expertId/chat'),
      body: {
        'message': message,
        'history': history
            .map((m) => m.toJson())
            .toList(),
      },
      token: token,
    );
  }

  Future<Map<String, dynamic>> rateBracket(
    String expertId,
    Map<String, String> bracket, {
    String? token,
  }) async {
    final response = await _client.post(
      _uri('/agents/$expertId/rate'),
      headers: _headers(token: token),
      body: jsonEncode({'bracket': bracket}),
    );
    _checkResponse(response);
    return jsonDecode(response.body)
        as Map<String, dynamic>;
  }

  void _checkResponse(http.Response response) {
    if (response.statusCode < 200 ||
        response.statusCode >= 300) {
      developer.log(
        'API error ${response.statusCode}: ${response.body}',
        name: 'ApiService',
      );

      final String userMessage;
      switch (response.statusCode) {
        case 401:
          userMessage = 'Please sign in to continue.';
          break;
        case 403:
          userMessage = 'Access denied.';
          break;
        case 404:
          userMessage = 'Not found.';
          break;
        default:
          userMessage = response.statusCode >= 500
              ? 'Server error. Please try again.'
              : 'Request failed. Please try again.';
      }

      throw ApiException(
        statusCode: response.statusCode,
        userMessage: userMessage,
        debugMessage: response.body,
      );
    }
  }
}
