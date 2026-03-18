import 'package:flutter/material.dart';
import 'package:march_madness/core/models/bracket_game.dart';

/// A single matchup card showing two teams, seeds, and win probabilities.
/// Styled like an ESPN bracket matchup cell.
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
    final borderColor = game.isUpset
        ? const Color(0xFFFF6D00) // orange for upsets
        : Colors.grey[700]!;

    return GestureDetector(
      onTap: onTap,
      child: Container(
        width: width,
        decoration: BoxDecoration(
          color: const Color(0xFF1A1A2E),
          borderRadius: BorderRadius.circular(4),
          border: Border.all(
            color: borderColor,
            width: game.isUpset ? 1.5 : 0.5,
          ),
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            _TeamRow(
              team: game.team1,
              seed: game.seed1,
              probability: game.team1Probability,
              isWinner: game.team1Wins,
              isTop: true,
            ),
            Container(
              height: 0.5,
              color: Colors.grey[700],
            ),
            _TeamRow(
              team: game.team2,
              seed: game.seed2,
              probability: game.team2Probability,
              isWinner: game.team2Wins,
              isTop: false,
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
  final bool isTop;

  const _TeamRow({
    required this.team,
    required this.seed,
    required this.probability,
    required this.isWinner,
    required this.isTop,
  });

  Color _probColor(double prob) {
    if (prob >= 0.75) return const Color(0xFF4CAF50);
    if (prob >= 0.50) return const Color(0xFFFFC107);
    return const Color(0xFFFF5722);
  }

  @override
  Widget build(BuildContext context) {
    final displayTeam = BracketGame.displayName(team);
    final prob = probability;

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 4),
      decoration: BoxDecoration(
        color: isWinner
            ? const Color(0xFF1B3A26) // dark green highlight for winner
            : Colors.transparent,
        borderRadius: BorderRadius.only(
          topLeft: isTop ? const Radius.circular(3) : Radius.zero,
          topRight: isTop ? const Radius.circular(3) : Radius.zero,
          bottomLeft: !isTop ? const Radius.circular(3) : Radius.zero,
          bottomRight: !isTop ? const Radius.circular(3) : Radius.zero,
        ),
      ),
      child: Row(
        children: [
          // Seed badge
          if (seed != null)
            Container(
              width: 20,
              height: 18,
              alignment: Alignment.center,
              margin: const EdgeInsets.only(right: 4),
              decoration: BoxDecoration(
                color: Colors.grey[800],
                borderRadius: BorderRadius.circular(2),
              ),
              child: Text(
                '$seed',
                style: TextStyle(
                  fontSize: 10,
                  fontWeight: FontWeight.w600,
                  color: isWinner ? Colors.white : Colors.grey[400],
                ),
              ),
            ),
          // Team name
          Expanded(
            child: Text(
              displayTeam,
              style: TextStyle(
                fontSize: 11,
                fontWeight: isWinner ? FontWeight.w700 : FontWeight.w400,
                color: isWinner ? Colors.white : Colors.grey[500],
              ),
              overflow: TextOverflow.ellipsis,
              maxLines: 1,
            ),
          ),
          // Win probability
          if (prob != null)
            Text(
              '${(prob * 100).toStringAsFixed(0)}%',
              style: TextStyle(
                fontSize: 10,
                fontWeight: FontWeight.w600,
                color: isWinner ? _probColor(prob) : Colors.grey[600],
              ),
            ),
        ],
      ),
    );
  }
}
