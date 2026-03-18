class AgentInfo {
  final String expertId;
  final String expertName;
  final String source;
  final String styleSummary;

  const AgentInfo({
    required this.expertId,
    required this.expertName,
    required this.source,
    required this.styleSummary,
  });

  factory AgentInfo.fromJson(
    Map<String, dynamic> json,
  ) {
    return AgentInfo(
      expertId:
          json['expert_id'] as String? ?? '',
      expertName:
          json['expert_name'] as String? ?? '',
      source: json['source'] as String? ?? '',
      styleSummary:
          json['style_summary'] as String? ?? '',
    );
  }
}
