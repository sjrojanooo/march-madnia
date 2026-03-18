import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:march_madness/core/models/bracket_game.dart';
import 'package:march_madness/data/repositories/bracket_repository.dart';
import 'package:march_madness/features/bracket/widgets/region_bracket.dart';
import 'package:march_madness/features/bracket/widgets/final_four_widget.dart';
import 'package:march_madness/features/bracket/widgets/game_detail_sheet.dart';

class BracketScreen extends StatefulWidget {
  const BracketScreen({super.key});

  @override
  State<BracketScreen> createState() => _BracketScreenState();
}

class _BracketScreenState extends State<BracketScreen> {
  late Future<BracketData> _future;

  @override
  void initState() {
    super.initState();
    _future = context.read<BracketRepository>().getBracket();
  }

  void _refresh() {
    setState(() {
      _future = context
          .read<BracketRepository>()
          .getBracket(forceRefresh: true);
    });
  }

  void _showDetail(BuildContext context, BracketGame game) {
    showModalBottomSheet(
      context: context,
      builder: (_) => GameDetailSheet(game: game),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('NCAA Tournament 2026'),
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh),
            onPressed: _refresh,
          ),
        ],
      ),
      body: FutureBuilder<BracketData>(
        future: _future,
        builder: (context, snapshot) {
          if (snapshot.connectionState == ConnectionState.waiting) {
            return const Center(child: CircularProgressIndicator());
          }
          if (snapshot.hasError) {
            _showError(context, snapshot.error.toString());
            return Center(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  const Icon(
                    Icons.error_outline,
                    size: 48,
                    color: Colors.orange,
                  ),
                  const SizedBox(height: 16),
                  Text(
                    'Failed to load bracket',
                    style: Theme.of(context).textTheme.titleMedium,
                  ),
                  const SizedBox(height: 8),
                  ElevatedButton(
                    onPressed: _refresh,
                    child: const Text('Retry'),
                  ),
                ],
              ),
            );
          }

          final data = snapshot.data!;
          return _BracketLayout(
            data: data,
            onGameTap: (game) => _showDetail(context, game),
          );
        },
      ),
    );
  }

  void _showError(BuildContext context, String message) {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(message),
          backgroundColor: Colors.red,
        ),
      );
    });
  }
}

/// The full ESPN-style bracket layout.
///
/// Layout (two rows):
/// ```
/// TOP ROW:
///   East (L->R: R64|R32|S16|E8)  |  Final Four Center  |  West (R->L: E8|S16|R32|R64)
///
/// BOTTOM ROW:
///   South (L->R: R64|R32|S16|E8)  |  Final Four Center  |  Midwest (R->L: E8|S16|R32|R64)
/// ```
class _BracketLayout extends StatelessWidget {
  final BracketData data;
  final void Function(BracketGame game) onGameTap;

  const _BracketLayout({
    required this.data,
    required this.onGameTap,
  });

  @override
  Widget build(BuildContext context) {
    final eastGames = data.regionGames['East'] ?? {};
    final westGames = data.regionGames['West'] ?? {};
    final southGames = data.regionGames['South'] ?? {};
    final midwestGames = data.regionGames['Midwest'] ?? {};

    return InteractiveViewer(
      constrained: false,
      boundaryMargin: const EdgeInsets.all(100),
      minScale: 0.15,
      maxScale: 2.0,
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.center,
          children: [
            // Top row: East | Final Four | West
            Row(
              crossAxisAlignment: CrossAxisAlignment.center,
              mainAxisSize: MainAxisSize.min,
              children: [
                // East region (left to right)
                RegionBracket(
                  region: 'East',
                  roundGames: eastGames,
                  mirrored: false,
                  onGameTap: onGameTap,
                ),
                const SizedBox(width: 32),
                // Final Four center (top half)
                FinalFourWidget(
                  finalFourGames: data.finalFour,
                  championship: data.championship,
                  onGameTap: onGameTap,
                ),
                const SizedBox(width: 32),
                // West region (right to left / mirrored)
                RegionBracket(
                  region: 'West',
                  roundGames: westGames,
                  mirrored: true,
                  onGameTap: onGameTap,
                ),
              ],
            ),
            const SizedBox(height: 48),
            // Divider
            Container(
              width: 800,
              height: 1,
              color: Colors.grey[800],
            ),
            const SizedBox(height: 48),
            // Bottom row: South | (spacer) | Midwest
            Row(
              crossAxisAlignment: CrossAxisAlignment.center,
              mainAxisSize: MainAxisSize.min,
              children: [
                // South region (left to right)
                RegionBracket(
                  region: 'South',
                  roundGames: southGames,
                  mirrored: false,
                  onGameTap: onGameTap,
                ),
                const SizedBox(width: 280),
                // Midwest region (right to left / mirrored)
                RegionBracket(
                  region: 'Midwest',
                  roundGames: midwestGames,
                  mirrored: true,
                  onGameTap: onGameTap,
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}
