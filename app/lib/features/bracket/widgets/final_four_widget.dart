import 'package:flutter/material.dart';
import 'package:march_madness/core/models/bracket_game.dart';
import 'package:march_madness/features/bracket/widgets/matchup_card.dart';

/// Displays the Final Four and Championship in the center of the bracket.
/// Layout:
///   FF Game 1
///   Championship
///   FF Game 2
class FinalFourWidget extends StatelessWidget {
  final List<BracketGame> finalFourGames;
  final BracketGame? championship;
  final void Function(BracketGame game)? onGameTap;

  const FinalFourWidget({
    super.key,
    required this.finalFourGames,
    this.championship,
    this.onGameTap,
  });

  @override
  Widget build(BuildContext context) {
    return Column(
      mainAxisAlignment: MainAxisAlignment.center,
      mainAxisSize: MainAxisSize.min,
      children: [
        // Header
        const Padding(
          padding: EdgeInsets.only(bottom: 12),
          child: Text(
            'FINAL FOUR',
            style: TextStyle(
              fontSize: 14,
              fontWeight: FontWeight.w800,
              color: Color(0xFF333333),
              letterSpacing: 1.5,
            ),
          ),
        ),

        // FF Game 1
        if (finalFourGames.isNotEmpty)
          Padding(
            padding: const EdgeInsets.only(bottom: 12),
            child: Column(
              children: [
                Text(
                  'Semifinal 1',
                  style: TextStyle(
                    fontSize: 10,
                    fontWeight: FontWeight.w600,
                    color: Colors.grey[600],
                  ),
                ),
                const SizedBox(height: 4),
                MatchupCard(
                  game: finalFourGames[0],
                  width: 190,
                  onTap: onGameTap != null
                      ? () => onGameTap!(finalFourGames[0])
                      : null,
                ),
              ],
            ),
          ),

        // Championship / Trophy
        if (championship != null)
          Padding(
            padding: const EdgeInsets.symmetric(vertical: 8),
            child: Column(
              children: [
                // Trophy icon
                const Icon(
                  Icons.emoji_events,
                  color: Color(0xFFD32F2F),
                  size: 32,
                ),
                const SizedBox(height: 4),
                const Text(
                  'CHAMPIONSHIP',
                  style: TextStyle(
                    fontSize: 11,
                    fontWeight: FontWeight.w800,
                    color: Color(0xFFD32F2F),
                    letterSpacing: 1.0,
                  ),
                ),
                const SizedBox(height: 6),
                MatchupCard(
                  game: championship!,
                  width: 200,
                  onTap: onGameTap != null
                      ? () => onGameTap!(championship!)
                      : null,
                ),
                // Champion banner
                if (championship!.winner != null)
                  Padding(
                    padding: const EdgeInsets.only(top: 8),
                    child: Container(
                      padding: const EdgeInsets.symmetric(
                        horizontal: 16,
                        vertical: 6,
                      ),
                      decoration: BoxDecoration(
                        color: const Color(0xFFD32F2F),
                        borderRadius: BorderRadius.circular(16),
                      ),
                      child: Text(
                        BracketGame.displayName(championship!.winner),
                        style: const TextStyle(
                          fontSize: 14,
                          fontWeight: FontWeight.w900,
                          color: Colors.white,
                        ),
                      ),
                    ),
                  ),
              ],
            ),
          ),

        // FF Game 2
        if (finalFourGames.length > 1)
          Padding(
            padding: const EdgeInsets.only(top: 12),
            child: Column(
              children: [
                Text(
                  'Semifinal 2',
                  style: TextStyle(
                    fontSize: 10,
                    fontWeight: FontWeight.w600,
                    color: Colors.grey[600],
                  ),
                ),
                const SizedBox(height: 4),
                MatchupCard(
                  game: finalFourGames[1],
                  width: 190,
                  onTap: onGameTap != null
                      ? () => onGameTap!(finalFourGames[1])
                      : null,
                ),
              ],
            ),
          ),
      ],
    );
  }
}
