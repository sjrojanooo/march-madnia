class BracketRating {
  final String expertId;
  final int rating;
  final String overallAssessment;
  final List<BracketSuggestion> suggestions;

  const BracketRating({
    required this.expertId,
    required this.rating,
    required this.overallAssessment,
    this.suggestions = const [],
  });

  factory BracketRating.fromJson(
    Map<String, dynamic> json,
  ) {
    final rawSuggestions =
        json['suggestions'] as List<dynamic>? ?? [];
    return BracketRating(
      expertId:
          json['expert_id'] as String? ?? '',
      rating: json['rating'] as int? ?? 0,
      overallAssessment:
          json['overall_assessment'] as String? ??
              '',
      suggestions: rawSuggestions
          .map(
            (s) => BracketSuggestion.fromJson(
              s as Map<String, dynamic>,
            ),
          )
          .toList(),
    );
  }
}

class BracketSuggestion {
  final String gameSlot;
  final String currentPick;
  final String suggestedPick;
  final String reasoning;

  const BracketSuggestion({
    required this.gameSlot,
    required this.currentPick,
    required this.suggestedPick,
    required this.reasoning,
  });

  factory BracketSuggestion.fromJson(
    Map<String, dynamic> json,
  ) {
    return BracketSuggestion(
      gameSlot:
          json['game_slot'] as String? ?? '',
      currentPick:
          json['current_pick'] as String? ?? '',
      suggestedPick:
          json['suggested_pick'] as String? ?? '',
      reasoning:
          json['reasoning'] as String? ?? '',
    );
  }
}
