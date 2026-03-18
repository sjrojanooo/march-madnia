class AgentMessage {
  final String role;
  final String content;
  final DateTime timestamp;

  const AgentMessage({
    required this.role,
    required this.content,
    required this.timestamp,
  });

  Map<String, dynamic> toJson() => {
        'role': role,
        'content': content,
      };
}
