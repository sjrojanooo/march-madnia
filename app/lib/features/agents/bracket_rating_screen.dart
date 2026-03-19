import 'dart:developer' as developer;

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:march_madness/core/models/agent_info.dart';
import 'package:march_madness/core/models/bracket_rating.dart';
import 'package:march_madness/data/repositories/agent_repository.dart';
import 'package:march_madness/features/agents/widgets/suggestion_card.dart';

class BracketRatingScreen extends StatefulWidget {
  const BracketRatingScreen({super.key});

  @override
  State<BracketRatingScreen> createState() =>
      _BracketRatingScreenState();
}

class _BracketRatingScreenState
    extends State<BracketRatingScreen> {
  String? _champion;
  final _finalFour = <String>['', '', '', ''];
  String? _selectedExpertId;
  BracketRating? _rating;
  bool _loading = false;
  List<AgentInfo>? _agents;

  static const _topTeams = [
    'Duke',
    'Auburn',
    'Florida',
    'Houston',
    'Tennessee',
    'Alabama',
    'Iowa State',
    'Kansas',
    'Purdue',
    'UConn',
    'Michigan State',
    'Arizona',
    'Gonzaga',
    'Marquette',
    'Kentucky',
    'Baylor',
  ];

  @override
  void initState() {
    super.initState();
    _loadAgents();
  }

  Future<void> _loadAgents() async {
    try {
      final agents = await context
          .read<AgentRepository>()
          .getAgents();
      setState(() {
        _agents = agents;
        if (agents.isNotEmpty) {
          _selectedExpertId =
              agents.first.expertId;
        }
      });
    } on Exception catch (e) {
      developer.log('Failed to load agents: $e', name: 'BracketRating');
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(
          const SnackBar(
            content: Text('Failed to load agents. Please try again.'),
            backgroundColor: Colors.red,
          ),
        );
      }
    }
  }

  Future<void> _submitRating() async {
    if (_selectedExpertId == null) return;
    if (_champion == null ||
        _champion!.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text(
            'Please pick a champion',
          ),
        ),
      );
      return;
    }

    setState(() => _loading = true);

    try {
      final bracket = <String, String>{
        'champion': _champion!,
        for (var i = 0;
            i < _finalFour.length;
            i++)
          'final_four_${i + 1}':
              _finalFour[i],
      };

      final repo =
          context.read<AgentRepository>();
      final rating = await repo.rateBracket(
        _selectedExpertId!,
        bracket,
      );
      setState(() => _rating = rating);
    } on Exception catch (e) {
      developer.log('Failed to rate bracket: $e', name: 'BracketRating');
      if (mounted) {
        ScaffoldMessenger.of(context)
            .showSnackBar(
          const SnackBar(
            content: Text('Failed to get rating. Please try again.'),
            backgroundColor: Colors.red,
          ),
        );
      }
    } finally {
      setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Rate My Bracket'),
      ),
      body: Center(
        child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 600),
        child: SingleChildScrollView(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment:
              CrossAxisAlignment.start,
          children: [
            _buildInputSection(),
            const SizedBox(height: 24),
            if (_rating != null)
              _buildRatingSection(),
          ],
        ),
      ),
      ),
      ),
    );
  }

  Widget _buildInputSection() {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment:
              CrossAxisAlignment.start,
          children: [
            Text(
              'Your Picks',
              style: Theme.of(context)
                  .textTheme
                  .titleMedium
                  ?.copyWith(
                    color: Colors.orange,
                  ),
            ),
            const SizedBox(height: 16),
            _dropdown(
              label: 'Champion',
              value: _champion,
              onChanged: (v) =>
                  setState(() => _champion = v),
            ),
            const SizedBox(height: 12),
            Text(
              'Final Four',
              style: Theme.of(context)
                  .textTheme
                  .bodyLarge,
            ),
            const SizedBox(height: 8),
            for (var i = 0; i < 4; i++) ...[
              _dropdown(
                label: 'Team ${i + 1}',
                value: _finalFour[i].isEmpty
                    ? null
                    : _finalFour[i],
                onChanged: (v) => setState(
                  () => _finalFour[i] = v ?? '',
                ),
              ),
              const SizedBox(height: 8),
            ],
            const SizedBox(height: 12),
            if (_agents != null &&
                _agents!.isNotEmpty)
              _agentDropdown(),
            const SizedBox(height: 16),
            SizedBox(
              width: double.infinity,
              child: ElevatedButton(
                onPressed:
                    _loading ? null : _submitRating,
                child: _loading
                    ? const SizedBox(
                        height: 20,
                        width: 20,
                        child:
                            CircularProgressIndicator(
                          strokeWidth: 2,
                        ),
                      )
                    : const Text('Get Rating'),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _dropdown({
    required String label,
    required String? value,
    required ValueChanged<String?> onChanged,
  }) {
    return DropdownButtonFormField<String>(
      initialValue: value,
      decoration: InputDecoration(
        labelText: label,
        isDense: true,
      ),
      items: _topTeams
          .map(
            (t) => DropdownMenuItem(
              value: t,
              child: Text(t),
            ),
          )
          .toList(),
      onChanged: onChanged,
    );
  }

  Widget _agentDropdown() {
    return DropdownButtonFormField<String>(
      initialValue: _selectedExpertId,
      decoration: const InputDecoration(
        labelText: 'Rating Expert',
        isDense: true,
      ),
      items: _agents!
          .map(
            (a) => DropdownMenuItem(
              value: a.expertId,
              child: Text(a.expertName),
            ),
          )
          .toList(),
      onChanged: (v) => setState(
        () => _selectedExpertId = v,
      ),
    );
  }

  Widget _buildRatingSection() {
    final r = _rating!;
    return Column(
      crossAxisAlignment:
          CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            ...List.generate(
              5,
              (i) => Icon(
                i < r.rating
                    ? Icons.star
                    : Icons.star_border,
                color: Colors.orange,
                size: 32,
              ),
            ),
            const SizedBox(width: 12),
            Text(
              '${r.rating}/5',
              style: Theme.of(context)
                  .textTheme
                  .headlineSmall,
            ),
          ],
        ),
        const SizedBox(height: 16),
        Text(
          'Assessment',
          style: Theme.of(context)
              .textTheme
              .titleMedium
              ?.copyWith(
                color: Colors.orange,
              ),
        ),
        const SizedBox(height: 8),
        Text(r.overallAssessment),
        if (r.suggestions.isNotEmpty) ...[
          const SizedBox(height: 16),
          Text(
            'Suggestions',
            style: Theme.of(context)
                .textTheme
                .titleMedium
                ?.copyWith(
                  color: Colors.orange,
                ),
          ),
          const SizedBox(height: 8),
          ...r.suggestions.map(
            (s) => SuggestionCard(
              suggestion: s,
            ),
          ),
        ],
      ],
    );
  }
}
