import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:march_madness/core/models/bracket_game.dart';
import 'package:march_madness/core/models/expert_profile.dart';
import 'package:march_madness/data/repositories/expert_repository.dart';

class GameDetailSheet extends StatelessWidget {
  final BracketGame game;

  const GameDetailSheet({
    super.key,
    required this.game,
  });

  @override
  Widget build(BuildContext context) {
    final prob = game.winProbability;
    return Container(
      padding: const EdgeInsets.all(20),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment:
            CrossAxisAlignment.start,
        children: [
          Text(
            game.gameSlot,
            style: Theme.of(context)
                .textTheme
                .titleLarge
                ?.copyWith(
                  color: Colors.orange,
                ),
          ),
          const SizedBox(height: 12),
          _row(
            'Matchup',
            '${_teamLabel(game.team1, game.seed1)}'
            ' vs '
            '${_teamLabel(game.team2, game.seed2)}',
          ),
          _row(
            'Winner',
            game.winner ?? 'TBD',
          ),
          if (prob != null)
            _row(
              'Win Probability',
              '${(prob * 100).toStringAsFixed(1)}%',
            ),
          _row(
            'Round',
            game.round.toString(),
          ),
          _row('Region', game.region),
          const SizedBox(height: 16),
          Text(
            'Expert Picks',
            style: Theme.of(context)
                .textTheme
                .titleMedium,
          ),
          const SizedBox(height: 8),
          _ExpertPicksList(
            gameSlot: game.gameSlot,
          ),
        ],
      ),
    );
  }

  String _teamLabel(String? team, int? seed) {
    if (team == null) return 'TBD';
    if (seed != null) return '($seed) $team';
    return team;
  }

  Widget _row(String label, String value) {
    return Padding(
      padding:
          const EdgeInsets.symmetric(vertical: 2),
      child: Row(
        children: [
          SizedBox(
            width: 130,
            child: Text(
              label,
              style: const TextStyle(
                color: Colors.grey,
              ),
            ),
          ),
          Expanded(
            child: Text(
              value,
              style: const TextStyle(
                fontWeight: FontWeight.w500,
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _ExpertPicksList extends StatefulWidget {
  final String gameSlot;

  const _ExpertPicksList({
    required this.gameSlot,
  });

  @override
  State<_ExpertPicksList> createState() =>
      _ExpertPicksListState();
}

class _ExpertPicksListState
    extends State<_ExpertPicksList> {
  late Future<Map<String, ExpertProfile>> _future;

  @override
  void initState() {
    super.initState();
    _future = context
        .read<ExpertRepository>()
        .getExperts();
  }

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<
        Map<String, ExpertProfile>>(
      future: _future,
      builder: (context, snapshot) {
        if (snapshot.connectionState ==
            ConnectionState.waiting) {
          return const SizedBox(
            height: 40,
            child: Center(
              child:
                  CircularProgressIndicator(),
            ),
          );
        }
        if (snapshot.hasError) {
          return const Text(
            'Could not load expert picks',
          );
        }

        final experts =
            snapshot.data!.values.toList();
        final picks = <String, String>{};
        for (final e in experts) {
          for (final round
              in e.picksByRound.values) {
            if (round.containsKey(
              widget.gameSlot,
            )) {
              picks[e.expertName] =
                  round[widget.gameSlot]!;
            }
          }
        }

        if (picks.isEmpty) {
          return const Text(
            'No expert picks for this game',
            style: TextStyle(
              color: Colors.grey,
            ),
          );
        }

        return Column(
          children: picks.entries
              .map(
                (e) => Padding(
                  padding:
                      const EdgeInsets.symmetric(
                    vertical: 2,
                  ),
                  child: Row(
                    children: [
                      SizedBox(
                        width: 130,
                        child: Text(
                          e.key,
                          style: const TextStyle(
                            color: Colors.grey,
                          ),
                        ),
                      ),
                      Text(e.value),
                    ],
                  ),
                ),
              )
              .toList(),
        );
      },
    );
  }
}
