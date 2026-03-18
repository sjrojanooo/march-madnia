import 'dart:developer' as developer;

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:march_madness/core/models/bracket_game.dart';
import 'package:march_madness/core/models/expert_profile.dart';
import 'package:march_madness/data/repositories/bracket_repository.dart';
import 'package:march_madness/data/repositories/expert_repository.dart';
import 'package:march_madness/features/bracket/widgets/region_bracket.dart';
import 'package:march_madness/features/bracket/widgets/final_four_widget.dart';

class ExpertPicksScreen extends StatefulWidget {
  const ExpertPicksScreen({super.key});

  @override
  State<ExpertPicksScreen> createState() => _ExpertPicksScreenState();
}

class _ExpertPicksScreenState extends State<ExpertPicksScreen> {
  late Future<_ExpertData> _future;
  String? _selectedExpertId;

  @override
  void initState() {
    super.initState();
    _future = _loadData();
  }

  Future<_ExpertData> _loadData() async {
    final bracketRepo = context.read<BracketRepository>();
    final expertRepo = context.read<ExpertRepository>();
    final bracketData = await bracketRepo.getBracket();
    final experts = await expertRepo.getExperts();
    return _ExpertData(bracketData: bracketData, experts: experts);
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Expert Brackets'),
      ),
      body: FutureBuilder<_ExpertData>(
        future: _future,
        builder: (context, snapshot) {
          if (snapshot.connectionState == ConnectionState.waiting) {
            return const Center(child: CircularProgressIndicator());
          }
          if (snapshot.hasError) {
            developer.log(
              'Expert data load error: ${snapshot.error}',
              name: 'ExpertPicksScreen',
            );
            return Center(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  const Icon(Icons.error_outline, size: 48, color: Colors.orange),
                  const SizedBox(height: 16),
                  Text(
                    'Failed to load expert data',
                    style: Theme.of(context).textTheme.titleMedium,
                  ),
                  const SizedBox(height: 4),
                  Text(
                    'Please try again later.',
                    style: TextStyle(fontSize: 12, color: Colors.grey[500]),
                    textAlign: TextAlign.center,
                  ),
                ],
              ),
            );
          }

          final data = snapshot.data!;
          if (data.experts.isEmpty) {
            return const Center(child: Text('No expert picks available'));
          }

          // Default to first expert
          final expertIds = data.experts.keys.toList();
          _selectedExpertId ??= expertIds.first;

          final expert = data.experts[_selectedExpertId]!;
          final expertBracket = _buildExpertBracket(expert, data.bracketData);

          return Column(
            children: [
              // Expert selector
              _ExpertSelector(
                experts: data.experts,
                selectedId: _selectedExpertId!,
                onChanged: (id) => setState(() => _selectedExpertId = id),
              ),
              // Expert bracket
              Expanded(
                child: _ExpertBracketLayout(
                  expert: expert,
                  regionGames: expertBracket.regionGames,
                  finalFour: expertBracket.finalFour,
                  championship: expertBracket.championship,
                ),
              ),
            ],
          );
        },
      ),
    );
  }

  /// Convert an expert's picks_by_round into a BracketData-like structure,
  /// using the model bracket as a template for seeds and matchup info.
  _ExpertBracketResult _buildExpertBracket(
    ExpertProfile expert,
    BracketData modelBracket,
  ) {
    final regionGames = <String, Map<int, List<BracketGame>>>{};
    final allModelGames = modelBracket.games;

    const regions = ['East', 'West', 'South', 'Midwest'];
    const roundKeys = ['R64', 'R32', 'S16', 'E8'];
    const roundNums = [1, 2, 3, 4];

    // Build seed-to-team lookup from R64 model games: {region: {seed: team_slug}}
    final seedToTeam = <String, Map<int, String>>{};
    for (final region in regions) {
      seedToTeam[region] = {};
      final r64 = modelBracket.regionGames[region]?[1] ?? [];
      for (final game in r64) {
        if (game.seed1 != null && game.team1 != null) {
          seedToTeam[region]![game.seed1!] = game.team1!;
        }
        if (game.seed2 != null && game.team2 != null) {
          seedToTeam[region]![game.seed2!] = game.team2!;
        }
      }
    }

    for (final region in regions) {
      regionGames[region] = {};
      for (int ri = 0; ri < roundKeys.length; ri++) {
        final roundKey = roundKeys[ri];
        final roundNum = roundNums[ri];

        // Get expert picks for this region+round
        final expertRoundPicks = expert.picksByRound[roundKey] ?? {};
        final regionPicks = <String, String>{};
        for (final entry in expertRoundPicks.entries) {
          if (entry.key.startsWith(region)) {
            regionPicks[entry.key] = entry.value;
          }
        }

        final games = <BracketGame>[];
        // Sort by game slot to maintain bracket order
        final sortedSlots = regionPicks.keys.toList()..sort();

        for (final slot in sortedSlots) {
          final winner = regionPicks[slot]!;
          // Try to get matchup info from model bracket
          final modelGame = allModelGames[slot];

          // Parse seeds from slot name (e.g., East_R32_1v9)
          final parts = slot.split('_');
          final seedPart = parts.length > 2 ? parts.last : '';
          final seedStrs = seedPart.split('v');
          final seed1 = int.tryParse(seedStrs.isNotEmpty ? seedStrs[0] : '');
          final seed2 = int.tryParse(seedStrs.length > 1 ? seedStrs[1] : '');

          // Resolve team names: model game first, then seed lookup
          final regionSeeds = seedToTeam[region] ?? {};
          final team1 = modelGame?.team1 ?? (seed1 != null ? regionSeeds[seed1] : null);
          final team2 = modelGame?.team2 ?? (seed2 != null ? regionSeeds[seed2] : null);

          games.add(BracketGame(
            gameSlot: slot,
            region: region,
            round: roundNum,
            team1: team1,
            team2: team2,
            seed1: seed1,
            seed2: seed2,
            winner: winner,
            winProbability: modelGame?.winProbability,
            isUpset: modelGame != null && modelGame.winner != winner,
          ));
        }

        if (games.isNotEmpty) {
          regionGames[region]![roundNum] = games;
        }
      }
    }

    // Get E8 winners from expert picks for FF team resolution
    final e8Picks = expert.picksByRound['E8'] ?? {};
    final e8WinnerByRegion = <String, String>{};
    for (final entry in e8Picks.entries) {
      for (final r in regions) {
        if (entry.key.startsWith(r)) {
          e8WinnerByRegion[r] = entry.value;
        }
      }
    }

    // Final Four — resolve teams from E8 winners
    final ffPicks = expert.picksByRound['FF'] ?? {};
    final ffGames = <BracketGame>[];
    for (final entry in ffPicks.entries) {
      // FF_EastvWest or FF_SouthvMidwest
      final ffParts = entry.key.replaceFirst('FF_', '').split('v');
      final team1 = ffParts.isNotEmpty ? e8WinnerByRegion[ffParts[0]] : null;
      final team2 = ffParts.length > 1 ? e8WinnerByRegion[ffParts[1]] : null;
      ffGames.add(BracketGame(
        gameSlot: entry.key,
        region: 'Final Four',
        round: 5,
        team1: team1,
        team2: team2,
        winner: entry.value,
      ));
    }

    // Championship — resolve teams from FF winners
    final champPicks = expert.picksByRound['Championship'] ?? {};
    BracketGame? championship;
    if (champPicks.isNotEmpty) {
      final entry = champPicks.entries.first;
      final ffWinners = ffGames.map((g) => g.winner).whereType<String>().toList();
      championship = BracketGame(
        gameSlot: entry.key,
        region: 'Championship',
        round: 6,
        team1: ffWinners.isNotEmpty ? ffWinners[0] : null,
        team2: ffWinners.length > 1 ? ffWinners[1] : null,
        winner: entry.value,
      );
    }

    return _ExpertBracketResult(
      regionGames: regionGames,
      finalFour: ffGames,
      championship: championship,
    );
  }
}

class _ExpertSelector extends StatelessWidget {
  final Map<String, ExpertProfile> experts;
  final String selectedId;
  final ValueChanged<String> onChanged;

  const _ExpertSelector({
    required this.experts,
    required this.selectedId,
    required this.onChanged,
  });

  @override
  Widget build(BuildContext context) {
    final expert = experts[selectedId]!;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
      decoration: BoxDecoration(
        color: Colors.grey[900],
        border: Border(bottom: BorderSide(color: Colors.grey[800]!)),
      ),
      child: Row(
        children: [
          // Dropdown
          Expanded(
            child: DropdownButtonHideUnderline(
              child: DropdownButton<String>(
                value: selectedId,
                isExpanded: true,
                dropdownColor: Colors.grey[850],
                items: experts.entries.map((e) {
                  return DropdownMenuItem(
                    value: e.key,
                    child: Row(
                      children: [
                        const Icon(Icons.person, size: 18, color: Colors.orange),
                        const SizedBox(width: 8),
                        Text(
                          e.value.expertName,
                          style: const TextStyle(fontWeight: FontWeight.w600),
                        ),
                        const SizedBox(width: 8),
                        Text(
                          e.value.source,
                          style: TextStyle(fontSize: 12, color: Colors.grey[500]),
                        ),
                      ],
                    ),
                  );
                }).toList(),
                onChanged: (v) {
                  if (v != null) onChanged(v);
                },
              ),
            ),
          ),
          const SizedBox(width: 16),
          // Champion chip
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
            decoration: BoxDecoration(
              gradient: const LinearGradient(
                colors: [Color(0xFFFF6D00), Color(0xFFFFD700)],
              ),
              borderRadius: BorderRadius.circular(16),
            ),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                const Icon(Icons.emoji_events, size: 16, color: Colors.black),
                const SizedBox(width: 4),
                Text(
                  BracketGame.displayName(expert.champion),
                  style: const TextStyle(
                    fontSize: 13,
                    fontWeight: FontWeight.w800,
                    color: Colors.black,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _ExpertBracketLayout extends StatelessWidget {
  final ExpertProfile expert;
  final Map<String, Map<int, List<BracketGame>>> regionGames;
  final List<BracketGame> finalFour;
  final BracketGame? championship;

  const _ExpertBracketLayout({
    required this.expert,
    required this.regionGames,
    required this.finalFour,
    required this.championship,
  });

  @override
  Widget build(BuildContext context) {
    final eastGames = regionGames['East'] ?? {};
    final westGames = regionGames['West'] ?? {};
    final southGames = regionGames['South'] ?? {};
    final midwestGames = regionGames['Midwest'] ?? {};

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
                RegionBracket(
                  region: 'East',
                  roundGames: eastGames,
                  mirrored: false,
                ),
                const SizedBox(width: 32),
                FinalFourWidget(
                  finalFourGames: finalFour,
                  championship: championship,
                ),
                const SizedBox(width: 32),
                RegionBracket(
                  region: 'West',
                  roundGames: westGames,
                  mirrored: true,
                ),
              ],
            ),
            const SizedBox(height: 48),
            Container(
              width: 800,
              height: 1,
              color: Colors.grey[800],
            ),
            const SizedBox(height: 48),
            // Bottom row: South | spacer | Midwest
            Row(
              crossAxisAlignment: CrossAxisAlignment.center,
              mainAxisSize: MainAxisSize.min,
              children: [
                RegionBracket(
                  region: 'South',
                  roundGames: southGames,
                  mirrored: false,
                ),
                const SizedBox(width: 280),
                RegionBracket(
                  region: 'Midwest',
                  roundGames: midwestGames,
                  mirrored: true,
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

class _ExpertData {
  final BracketData bracketData;
  final Map<String, ExpertProfile> experts;

  const _ExpertData({
    required this.bracketData,
    required this.experts,
  });
}

class _ExpertBracketResult {
  final Map<String, Map<int, List<BracketGame>>> regionGames;
  final List<BracketGame> finalFour;
  final BracketGame? championship;

  const _ExpertBracketResult({
    required this.regionGames,
    required this.finalFour,
    required this.championship,
  });
}
