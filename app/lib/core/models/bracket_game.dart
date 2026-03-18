class BracketGame {
  final String gameSlot;
  final String region;
  final int round;
  final String? winner;
  final double? winProbability;
  final int? seed1;
  final int? seed2;
  final String? team1;
  final String? team2;
  final bool isUpset;

  const BracketGame({
    required this.gameSlot,
    required this.region,
    required this.round,
    this.winner,
    this.winProbability,
    this.seed1,
    this.seed2,
    this.team1,
    this.team2,
    this.isUpset = false,
  });

  factory BracketGame.fromJson(
    String slot,
    Map<String, dynamic> json,
  ) {
    return BracketGame(
      gameSlot: slot,
      region: json['region'] as String? ?? '',
      round: (json['round'] as num?)?.toInt() ?? 0,
      winner: json['winner'] as String?,
      winProbability:
          (json['win_probability'] as num?)?.toDouble(),
      seed1: (json['seed_1'] as num?)?.toInt(),
      seed2: (json['seed_2'] as num?)?.toInt(),
      team1: json['team_1'] as String?,
      team2: json['team_2'] as String?,
    );
  }

  /// Parse from API game_predictions format.
  factory BracketGame.fromPrediction(Map<String, dynamic> pred) {
    final label = pred['game_label'] as String;
    final roundNum = _parseRound(label);
    final region = _parseRegion(label);

    return BracketGame(
      gameSlot: label,
      region: region,
      round: roundNum,
      winner: pred['predicted_winner'] as String?,
      winProbability: (pred['win_probability'] as num?)?.toDouble(),
      seed1: (pred['seed_a'] as num?)?.toInt(),
      seed2: (pred['seed_b'] as num?)?.toInt(),
      team1: pred['team_a'] as String?,
      team2: pred['team_b'] as String?,
      isUpset: pred['upset'] == true,
    );
  }

  static int _parseRound(String label) {
    if (label.contains('R64')) return 1;
    if (label.contains('R32')) return 2;
    if (label.contains('S16')) return 3;
    if (label.contains('E8')) return 4;
    if (label.startsWith('FF')) return 5;
    if (label.startsWith('Championship')) return 6;
    return 0;
  }

  static String _parseRegion(String label) {
    if (label.startsWith('East')) return 'East';
    if (label.startsWith('West')) return 'West';
    if (label.startsWith('South')) return 'South';
    if (label.startsWith('Midwest')) return 'Midwest';
    if (label.startsWith('FF')) return 'Final Four';
    if (label.startsWith('Championship')) return 'Championship';
    return '';
  }

  /// Display name for a team slug (title case, replace hyphens).
  static String displayName(String? slug) {
    if (slug == null || slug.isEmpty) return 'TBD';
    return slug
        .replaceAll('-', ' ')
        .split(' ')
        .map((w) => w.isEmpty
            ? ''
            : '${w[0].toUpperCase()}${w.substring(1).toLowerCase()}')
        .join(' ');
  }

  /// Whether team1 is the predicted winner.
  bool get team1Wins => winner != null && winner == team1;

  /// Whether team2 is the predicted winner.
  bool get team2Wins => winner != null && winner == team2;

  /// Win probability for team 1 (complement of team 2).
  double? get team1Probability {
    if (winProbability == null) return null;
    return team1Wins ? winProbability : 1.0 - winProbability!;
  }

  /// Win probability for team 2.
  double? get team2Probability {
    if (winProbability == null) return null;
    return team2Wins ? winProbability : 1.0 - winProbability!;
  }
}
