import 'package:flutter/material.dart';
import 'package:march_madness/core/models/bracket_game.dart';

class GameSlotTile extends StatelessWidget {
  final BracketGame game;

  const GameSlotTile({
    super.key,
    required this.game,
  });

  Color _confidenceColor(double? prob) {
    if (prob == null) return Colors.grey;
    if (prob > 0.75) return Colors.green;
    if (prob > 0.50) return Colors.yellow;
    return Colors.orange;
  }

  @override
  Widget build(BuildContext context) {
    final prob = game.winProbability;
    final color = _confidenceColor(prob);
    final winner =
        game.winner ?? 'TBD';
    final seedText = game.seed1 != null
        ? '(${game.seed1})'
        : '';

    return Card(
      margin: const EdgeInsets.symmetric(
        vertical: 4,
        horizontal: 2,
      ),
      child: Padding(
        padding: const EdgeInsets.all(8),
        child: Column(
          crossAxisAlignment:
              CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Expanded(
                  child: Text(
                    '$seedText $winner',
                    style: const TextStyle(
                      fontWeight: FontWeight.w600,
                      fontSize: 13,
                    ),
                    overflow: TextOverflow.ellipsis,
                  ),
                ),
                Text(
                  'R${game.round}',
                  style: TextStyle(
                    color: Colors.grey[500],
                    fontSize: 11,
                  ),
                ),
              ],
            ),
            const SizedBox(height: 4),
            if (prob != null)
              ClipRRect(
                borderRadius:
                    BorderRadius.circular(4),
                child: LinearProgressIndicator(
                  value: prob,
                  backgroundColor:
                      Colors.grey[800],
                  valueColor:
                      AlwaysStoppedAnimation(
                    color,
                  ),
                  minHeight: 6,
                ),
              ),
            if (prob != null)
              Padding(
                padding:
                    const EdgeInsets.only(top: 2),
                child: Text(
                  '${(prob * 100).toStringAsFixed(0)}%',
                  style: TextStyle(
                    color: color,
                    fontSize: 11,
                  ),
                ),
              ),
          ],
        ),
      ),
    );
  }
}
