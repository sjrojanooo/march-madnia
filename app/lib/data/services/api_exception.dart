class ApiException implements Exception {
  final int statusCode;
  final String userMessage;
  final String? debugMessage;

  ApiException({
    required this.statusCode,
    required this.userMessage,
    this.debugMessage,
  });

  @override
  String toString() => userMessage;
}
