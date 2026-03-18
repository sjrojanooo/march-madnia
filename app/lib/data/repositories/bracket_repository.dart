import 'package:march_madness/core/models/bracket_game.dart';
import 'package:march_madness/data/services/api_service.dart';

/// Holds the parsed bracket: best-path games organized by region and round,
/// plus the Final Four and Championship.
class BracketData {
  /// All 63 best-path games keyed by game_label.
  final Map<String, BracketGame> games;

  /// Games grouped: region -> round -> list of games (sorted by seed).
  /// Regions: East, West, South, Midwest.
  /// Rounds: 1 (R64), 2 (R32), 3 (S16), 4 (E8).
  final Map<String, Map<int, List<BracketGame>>> regionGames;

  /// Final Four games (round 5) — 2 games.
  final List<BracketGame> finalFour;

  /// Championship game (round 6) — 1 game.
  final BracketGame? championship;

  /// Advancement probabilities: team_slug -> round_name -> probability.
  final Map<String, Map<String, double>> advancementProbabilities;

  /// Champion probabilities: team_slug -> probability.
  final Map<String, double> championProbabilities;

  const BracketData({
    required this.games,
    required this.regionGames,
    required this.finalFour,
    required this.championship,
    this.advancementProbabilities = const {},
    this.championProbabilities = const {},
  });
}

class BracketRepository {
  final ApiService _api;
  BracketData? _cache;

  BracketRepository(this._api);

  Future<BracketData> getBracket({
    bool forceRefresh = false,
  }) async {
    if (_cache != null && !forceRefresh) {
      return _cache!;
    }

    final data = await _api.getBracket();
    _cache = _parseBracketData(data);
    return _cache!;
  }

  void clearCache() => _cache = null;

  BracketData _parseBracketData(Map<String, dynamic> data) {
    // 1. Index all predictions by game_label.
    final predictions = data['game_predictions'] as List<dynamic>? ?? [];
    final predByLabel = <String, Map<String, dynamic>>{};
    for (final p in predictions) {
      final pred = p as Map<String, dynamic>;
      final label = pred['game_label'] as String;
      predByLabel[label] = pred;
    }

    // 2. best_bracket has {game_label: winner_slug} for ALL possible paths.
    //    We need to trace the actual best path through the bracket.
    final bestBracket = data['best_bracket'] as Map<String, dynamic>? ?? {};

    // 3. Parse advancement/champion probabilities.
    final advProbs = <String, Map<String, double>>{};
    final rawAdv =
        data['advancement_probabilities'] as Map<String, dynamic>? ?? {};
    for (final entry in rawAdv.entries) {
      final rounds = entry.value as Map<String, dynamic>;
      advProbs[entry.key] = rounds.map(
        (k, v) => MapEntry(k, (v as num).toDouble()),
      );
    }

    final champProbs = <String, double>{};
    final rawChamp =
        data['champion_probabilities'] as Map<String, dynamic>? ?? {};
    for (final entry in rawChamp.entries) {
      champProbs[entry.key] = (entry.value as num).toDouble();
    }

    // 4. Build the best-path bracket by tracing round-by-round.
    final allGames = <String, BracketGame>{};
    final regionGames = <String, Map<int, List<BracketGame>>>{};

    const regions = ['East', 'West', 'South', 'Midwest'];
    // Standard bracket seed matchups for R64:
    // 1v16, 8v9, 5v12, 4v13, 6v11, 3v14, 7v10, 2v15
    const r64Matchups = [
      [1, 16],
      [8, 9],
      [5, 12],
      [4, 13],
      [6, 11],
      [3, 14],
      [7, 10],
      [2, 15],
    ];

    // R32 matchup pairs (indices into r64Matchups that play each other):
    // Winner of 1v16 plays winner of 8v9, etc.
    const r32Pairs = [
      [0, 1], // top quarter
      [2, 3],
      [4, 5],
      [6, 7],
    ];

    // S16 pairs (indices into r32 results):
    const s16Pairs = [
      [0, 1],
      [2, 3],
    ];

    // Track winners per region per round for forward-tracing.
    final regionWinners = <String, List<List<String?>>>{};

    for (final region in regions) {
      regionGames[region] = {};
      regionWinners[region] = [];

      // --- R64 ---
      final r64Games = <BracketGame>[];
      final r64Winners = <String?>[];

      for (final matchup in r64Matchups) {
        final label = '${region}_R64_${matchup[0]}v${matchup[1]}';
        final pred = predByLabel[label];
        if (pred != null) {
          final game = BracketGame.fromPrediction(pred);
          r64Games.add(game);
          allGames[label] = game;
          r64Winners.add(game.winner);
        } else {
          // Fallback: create from best_bracket if prediction not found.
          final winner = bestBracket[label] as String?;
          final game = BracketGame(
            gameSlot: label,
            region: region,
            round: 1,
            seed1: matchup[0],
            seed2: matchup[1],
            winner: winner,
          );
          r64Games.add(game);
          allGames[label] = game;
          r64Winners.add(winner);
        }
      }
      regionGames[region]![1] = r64Games;
      regionWinners[region]!.add(r64Winners);

      // --- R32 ---
      final r32Games = <BracketGame>[];
      final r32Winners = <String?>[];

      for (final pair in r32Pairs) {
        final topGame = r64Games[pair[0]];
        final botGame = r64Games[pair[1]];
        final topWinner = r64Winners[pair[0]];
        final botWinner = r64Winners[pair[1]];

        // Find the seed of the winner to construct game_label.
        final topSeed = _winnerSeed(topGame);
        final botSeed = _winnerSeed(botGame);

        if (topSeed != null && botSeed != null) {
          final label = '${region}_R32_${topSeed}v$botSeed';
          final pred = predByLabel[label];
          if (pred != null) {
            final game = BracketGame.fromPrediction(pred);
            r32Games.add(game);
            allGames[label] = game;
            r32Winners.add(game.winner);
          } else {
            final winner = bestBracket[label] as String?;
            final game = BracketGame(
              gameSlot: label,
              region: region,
              round: 2,
              seed1: topSeed,
              seed2: botSeed,
              team1: topWinner,
              team2: botWinner,
              winner: winner,
            );
            r32Games.add(game);
            allGames[label] = game;
            r32Winners.add(winner);
          }
        } else {
          // Seeds unknown, add placeholder.
          r32Games.add(BracketGame(
            gameSlot: '${region}_R32_?',
            region: region,
            round: 2,
          ));
          r32Winners.add(null);
        }
      }
      regionGames[region]![2] = r32Games;
      regionWinners[region]!.add(r32Winners);

      // --- S16 ---
      final s16Games = <BracketGame>[];
      final s16Winners = <String?>[];

      for (final pair in s16Pairs) {
        final topGame = r32Games[pair[0]];
        final botGame = r32Games[pair[1]];

        final topSeed = _winnerSeed(topGame);
        final botSeed = _winnerSeed(botGame);

        if (topSeed != null && botSeed != null) {
          final label = '${region}_S16_${topSeed}v$botSeed';
          final pred = predByLabel[label];
          if (pred != null) {
            final game = BracketGame.fromPrediction(pred);
            s16Games.add(game);
            allGames[label] = game;
            s16Winners.add(game.winner);
          } else {
            final winner = bestBracket[label] as String?;
            final game = BracketGame(
              gameSlot: label,
              region: region,
              round: 3,
              seed1: topSeed,
              seed2: botSeed,
              winner: winner,
            );
            s16Games.add(game);
            allGames[label] = game;
            s16Winners.add(winner);
          }
        } else {
          s16Games.add(BracketGame(
            gameSlot: '${region}_S16_?',
            region: region,
            round: 3,
          ));
          s16Winners.add(null);
        }
      }
      regionGames[region]![3] = s16Games;
      regionWinners[region]!.add(s16Winners);

      // --- E8 (Elite Eight) ---
      final topS16 = s16Games.isNotEmpty ? s16Games[0] : null;
      final botS16 = s16Games.length > 1 ? s16Games[1] : null;
      final topSeed = topS16 != null ? _winnerSeed(topS16) : null;
      final botSeed = botS16 != null ? _winnerSeed(botS16) : null;

      if (topSeed != null && botSeed != null) {
        final label = '${region}_E8_${topSeed}v$botSeed';
        final pred = predByLabel[label];
        if (pred != null) {
          final game = BracketGame.fromPrediction(pred);
          regionGames[region]![4] = [game];
          allGames[label] = game;
          regionWinners[region]!.add([game.winner]);
        } else {
          final winner = bestBracket[label] as String?;
          final game = BracketGame(
            gameSlot: label,
            region: region,
            round: 4,
            seed1: topSeed,
            seed2: botSeed,
            winner: winner,
          );
          regionGames[region]![4] = [game];
          allGames[label] = game;
          regionWinners[region]!.add([winner]);
        }
      } else {
        regionGames[region]![4] = [
          BracketGame(
            gameSlot: '${region}_E8_?',
            region: region,
            round: 4,
          )
        ];
        regionWinners[region]!.add([null]);
      }
    }

    // --- Final Four ---
    // FF games: typically East vs West (FF1) and South vs Midwest (FF2).
    // Look for FF labels in best_bracket/predictions.
    final ffGames = <BracketGame>[];

    // Try standard FF label patterns.
    final ffLabels = predByLabel.keys
        .where((k) => k.startsWith('FF_'))
        .toList();

    // Also check best_bracket for FF keys.
    final ffBestKeys = bestBracket.keys
        .where((k) => k.startsWith('FF_'))
        .toList();

    // Use the predictions that match the best path winners.
    // Get E8 winners per region.
    final e8Winners = <String, String?>{};
    for (final region in regions) {
      final e8List = regionGames[region]?[4];
      if (e8List != null && e8List.isNotEmpty) {
        e8Winners[region] = e8List[0].winner;
      }
    }

    // Find FF games that match E8 winners.
    BracketGame? ff1;
    BracketGame? ff2;

    for (final label in ffLabels) {
      final pred = predByLabel[label]!;
      final teamA = pred['team_a'] as String?;
      final teamB = pred['team_b'] as String?;

      // Check if both teams are E8 winners.
      final isE8WinnerA = e8Winners.values.contains(teamA);
      final isE8WinnerB = e8Winners.values.contains(teamB);

      if (isE8WinnerA && isE8WinnerB) {
        final game = BracketGame.fromPrediction(pred);
        allGames[label] = game;
        if (ff1 == null) {
          ff1 = game;
        } else {
          ff2 ??= game;
        }
      }
    }

    // Fallback: if we didn't find FF games in predictions, build from E8 winners.
    if (ff1 == null && e8Winners.isNotEmpty) {
      // Look through all FF best_bracket keys.
      for (final key in ffBestKeys) {
        final pred = predByLabel[key];
        if (pred != null) {
          final game = BracketGame.fromPrediction(pred);
          allGames[key] = game;
          if (ff1 == null) {
            ff1 = game;
          } else {
            ff2 ??= game;
          }
        }
      }
    }

    if (ff1 != null) ffGames.add(ff1);
    if (ff2 != null) ffGames.add(ff2);

    // --- Championship ---
    BracketGame? championship;

    final champLabels = predByLabel.keys
        .where((k) => k.startsWith('Championship'))
        .toList();

    // Find championship game matching FF winners.
    final ffWinners = ffGames.map((g) => g.winner).whereType<String>().toSet();

    for (final label in champLabels) {
      final pred = predByLabel[label]!;
      final teamA = pred['team_a'] as String?;
      final teamB = pred['team_b'] as String?;

      if (ffWinners.contains(teamA) && ffWinners.contains(teamB)) {
        championship = BracketGame.fromPrediction(pred);
        allGames[label] = championship;
        break;
      }
    }

    // Fallback: check best_bracket for Championship keys.
    if (championship == null) {
      final champBestKeys = bestBracket.keys
          .where((k) => k.startsWith('Championship'))
          .toList();
      for (final key in champBestKeys) {
        final pred = predByLabel[key];
        if (pred != null) {
          final teamA = pred['team_a'] as String?;
          final teamB = pred['team_b'] as String?;
          if (ffWinners.contains(teamA) && ffWinners.contains(teamB)) {
            championship = BracketGame.fromPrediction(pred);
            allGames[key] = championship;
            break;
          }
        }
      }
    }

    return BracketData(
      games: allGames,
      regionGames: regionGames,
      finalFour: ffGames,
      championship: championship,
      advancementProbabilities: advProbs,
      championProbabilities: champProbs,
    );
  }

  /// Get the seed of the predicted winner from a game.
  int? _winnerSeed(BracketGame game) {
    if (game.winner == null) return null;
    if (game.winner == game.team1) return game.seed1;
    if (game.winner == game.team2) return game.seed2;
    // Fallback: try matching by slug.
    return game.seed1;
  }
}
