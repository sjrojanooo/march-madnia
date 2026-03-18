import 'package:flutter/material.dart';
import 'package:march_madness/core/models/bracket_game.dart';
import 'package:march_madness/features/bracket/widgets/matchup_card.dart';
import 'package:march_madness/features/bracket/widgets/bracket_connector.dart';

/// Displays one region's bracket as columns: R64 -> R32 -> S16 -> E8.
/// When [mirrored] is true, columns go right-to-left (E8 -> S16 -> R32 -> R64).
class RegionBracket extends StatelessWidget {
  final String region;
  final Map<int, List<BracketGame>> roundGames;
  final bool mirrored;
  final void Function(BracketGame game)? onGameTap;

  static const double matchupCardWidth = 170.0;
  static const double matchupCardHeight = 48.0;
  static const double connectorWidth = 24.0;
  static const double baseGap = 8.0;

  const RegionBracket({
    super.key,
    required this.region,
    required this.roundGames,
    this.mirrored = false,
    this.onGameTap,
  });

  @override
  Widget build(BuildContext context) {
    // Rounds in display order: R64(1), R32(2), S16(3), E8(4).
    // If mirrored, reverse the order.
    final rounds = mirrored ? [4, 3, 2, 1] : [1, 2, 3, 4];
    final roundLabels = {
      1: 'R64',
      2: 'R32',
      3: 'S16',
      4: 'E8',
    };

    final columns = <Widget>[];

    for (int i = 0; i < rounds.length; i++) {
      final round = rounds[i];
      final games = roundGames[round] ?? [];
      final gapMultiplier = _gapMultiplier(round);

      // Add the matchup column.
      columns.add(
        _RoundColumn(
          roundLabel: roundLabels[round]!,
          games: games,
          gapMultiplier: gapMultiplier,
          round: round,
          onGameTap: onGameTap,
        ),
      );

      // Add connector lines between rounds (not after the last column).
      if (i < rounds.length - 1) {
        final connectorRound = mirrored ? rounds[i + 1] : round;
        final connectorGames = roundGames[connectorRound]?.length ?? 0;
        final connectorGap = baseGap * _gapMultiplier(connectorRound);

        columns.add(
          SizedBox(
            width: connectorWidth,
            height: _columnHeight(connectorGames, connectorGap),
            child: CustomPaint(
              size: Size(
                connectorWidth,
                _columnHeight(connectorGames, connectorGap),
              ),
              painter: BracketConnectorPainter(
                gamesInRound: connectorGames,
                matchupHeight: matchupCardHeight,
                gapBetweenMatchups: connectorGap,
                mirrored: mirrored,
              ),
            ),
          ),
        );
      }
    }

    return Column(
      crossAxisAlignment: CrossAxisAlignment.center,
      children: [
        // Region header
        Padding(
          padding: const EdgeInsets.only(bottom: 8, top: 4),
          child: Text(
            region.toUpperCase(),
            style: const TextStyle(
              fontSize: 14,
              fontWeight: FontWeight.w800,
              color: Color(0xFFFF6D00),
              letterSpacing: 1.5,
            ),
          ),
        ),
        Row(
          crossAxisAlignment: CrossAxisAlignment.center,
          mainAxisSize: MainAxisSize.min,
          children: columns,
        ),
      ],
    );
  }

  double _gapMultiplier(int round) {
    // Each round doubles the spacing.
    switch (round) {
      case 1:
        return 1.0;
      case 2:
        return 3.0;
      case 3:
        return 7.0;
      case 4:
        return 15.0;
      default:
        return 1.0;
    }
  }

  double _columnHeight(int gameCount, double gap) {
    if (gameCount == 0) return matchupCardHeight;
    return gameCount * matchupCardHeight + (gameCount - 1) * gap;
  }
}

class _RoundColumn extends StatelessWidget {
  final String roundLabel;
  final List<BracketGame> games;
  final double gapMultiplier;
  final int round;
  final void Function(BracketGame game)? onGameTap;

  const _RoundColumn({
    required this.roundLabel,
    required this.games,
    required this.gapMultiplier,
    required this.round,
    this.onGameTap,
  });

  @override
  Widget build(BuildContext context) {
    final gap = RegionBracket.baseGap * gapMultiplier;

    return Column(
      mainAxisAlignment: MainAxisAlignment.center,
      mainAxisSize: MainAxisSize.min,
      children: [
        // Round label header
        Padding(
          padding: const EdgeInsets.only(bottom: 6),
          child: Text(
            roundLabel,
            style: TextStyle(
              fontSize: 10,
              fontWeight: FontWeight.w600,
              color: Colors.grey[500],
              letterSpacing: 0.5,
            ),
          ),
        ),
        // Game cards with spacing
        ...List.generate(games.length, (i) {
          return Padding(
            padding: EdgeInsets.only(bottom: i < games.length - 1 ? gap : 0),
            child: MatchupCard(
              game: games[i],
              width: RegionBracket.matchupCardWidth,
              onTap: onGameTap != null ? () => onGameTap!(games[i]) : null,
            ),
          );
        }),
      ],
    );
  }
}
