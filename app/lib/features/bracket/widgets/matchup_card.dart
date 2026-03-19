import 'package:flutter/material.dart';
import 'package:march_madness/core/models/bracket_game.dart';

/// ESPN Tournament Challenge style matchup card.
/// White card with two team rows, seed badges, and win probability.
class MatchupCard extends StatelessWidget {
  final BracketGame game;
  final VoidCallback? onTap;
  final double width;

  const MatchupCard({
    super.key,
    required this.game,
    this.onTap,
    this.width = 180,
  });

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        width: width,
        decoration: BoxDecoration(
          color: Colors.white,
          border: Border.all(color: const Color(0xFFD0D0D0), width: 1),
          borderRadius: BorderRadius.circular(2),
          boxShadow: const [
            BoxShadow(
              color: Color(0x0D000000),
              blurRadius: 2,
              offset: Offset(0, 1),
            ),
          ],
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            _TeamRow(
              team: game.team1,
              seed: game.seed1,
              probability: game.team1Probability,
              isWinner: game.team1Wins,
            ),
            Container(height: 1, color: const Color(0xFFE0E0E0)),
            _TeamRow(
              team: game.team2,
              seed: game.seed2,
              probability: game.team2Probability,
              isWinner: game.team2Wins,
            ),
          ],
        ),
      ),
    );
  }
}

class _TeamRow extends StatelessWidget {
  final String? team;
  final int? seed;
  final double? probability;
  final bool isWinner;

  const _TeamRow({
    required this.team,
    required this.seed,
    required this.probability,
    required this.isWinner,
  });

  @override
  Widget build(BuildContext context) {
    final displayTeam = BracketGame.displayName(team);
    final isTbd = team == null || team!.isEmpty;

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 5),
      decoration: BoxDecoration(
        color: isWinner ? const Color(0xFFFFFDE7) : Colors.white,
      ),
      child: Row(
        children: [
          // Seed badge
          if (seed != null)
            Container(
              width: 18,
              height: 18,
              alignment: Alignment.center,
              margin: const EdgeInsets.only(right: 6),
              child: Text(
                '$seed',
                style: TextStyle(
                  fontSize: 11,
                  fontWeight: FontWeight.w600,
                  color: Colors.grey[600],
                ),
              ),
            ),
          // Team name
          Expanded(
            child: Text(
              displayTeam,
              style: TextStyle(
                fontSize: 12,
                fontWeight: isWinner ? FontWeight.w800 : FontWeight.w500,
                color: isTbd
                    ? Colors.grey[400]
                    : isWinner
                        ? Colors.black
                        : const Color(0xFF333333),
              ),
              overflow: TextOverflow.ellipsis,
              maxLines: 1,
            ),
          ),
          // Win probability
          if (probability != null)
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 4, vertical: 1),
              child: Text(
                '${(probability! * 100).toStringAsFixed(0)}%',
                style: TextStyle(
                  fontSize: 10,
                  fontWeight: FontWeight.w600,
                  color: isWinner
                      ? const Color(0xFF2E7D32)
                      : Colors.grey[500],
                ),
              ),
            ),
        ],
      ),
    );
  }
}
