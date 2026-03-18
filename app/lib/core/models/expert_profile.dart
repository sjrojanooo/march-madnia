class ExpertProfile {
  final String expertId;
  final String expertName;
  final String source;
  final String? champion;
  final List<String> finalFour;
  final Map<String, Map<String, String>> picksByRound;

  const ExpertProfile({
    required this.expertId,
    required this.expertName,
    required this.source,
    this.champion,
    this.finalFour = const [],
    this.picksByRound = const {},
  });

  factory ExpertProfile.fromJson(
    String id,
    Map<String, dynamic> json,
  ) {
    final rawPicks =
        json['picks_by_round'] as Map<String, dynamic>?;
    final picksByRound = <String, Map<String, String>>{};
    if (rawPicks != null) {
      for (final entry in rawPicks.entries) {
        final roundPicks =
            entry.value as Map<String, dynamic>;
        picksByRound[entry.key] = roundPicks.map(
          (k, v) => MapEntry(k, v.toString()),
        );
      }
    }

    final rawFf = json['final_four'] as List<dynamic>?;

    return ExpertProfile(
      expertId: id,
      expertName:
          json['expert_name'] as String? ?? id,
      source: json['source'] as String? ?? '',
      champion: json['champion'] as String?,
      finalFour: rawFf
              ?.map((e) => e.toString())
              .toList() ??
          [],
      picksByRound: picksByRound,
    );
  }
}
