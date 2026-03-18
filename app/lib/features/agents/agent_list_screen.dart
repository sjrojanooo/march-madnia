import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:provider/provider.dart';
import 'package:march_madness/core/models/agent_info.dart';
import 'package:march_madness/data/repositories/agent_repository.dart';

class AgentListScreen extends StatefulWidget {
  const AgentListScreen({super.key});

  @override
  State<AgentListScreen> createState() =>
      _AgentListScreenState();
}

class _AgentListScreenState
    extends State<AgentListScreen> {
  late Future<List<AgentInfo>> _future;

  @override
  void initState() {
    super.initState();
    _future = context
        .read<AgentRepository>()
        .getAgents();
  }

  IconData _iconForSource(String source) {
    switch (source.toLowerCase()) {
      case 'espn':
        return Icons.tv;
      case 'cbs':
        return Icons.live_tv;
      case 'model':
        return Icons.analytics;
      case 'fan':
        return Icons.person;
      default:
        return Icons.sports_basketball;
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Expert Agents'),
      ),
      body: FutureBuilder<List<AgentInfo>>(
        future: _future,
        builder: (context, snapshot) {
          if (snapshot.connectionState ==
              ConnectionState.waiting) {
            return const Center(
              child: CircularProgressIndicator(),
            );
          }
          if (snapshot.hasError) {
            _showError(
              snapshot.error.toString(),
            );
            return const Center(
              child: Text(
                'Failed to load agents',
              ),
            );
          }

          final agents = snapshot.data!;
          if (agents.isEmpty) {
            return const Center(
              child: Text(
                'No agents available',
              ),
            );
          }

          return ListView.builder(
            padding: const EdgeInsets.all(12),
            itemCount: agents.length,
            itemBuilder: (context, index) {
              final agent = agents[index];
              return Card(
                child: ListTile(
                  leading: CircleAvatar(
                    backgroundColor:
                        Colors.orange,
                    child: Icon(
                      _iconForSource(
                        agent.source,
                      ),
                      color: Colors.black,
                    ),
                  ),
                  title: Text(
                    agent.expertName,
                    style: const TextStyle(
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                  subtitle: Column(
                    crossAxisAlignment:
                        CrossAxisAlignment.start,
                    children: [
                      Text(
                        agent.source,
                        style: TextStyle(
                          color: Colors.grey[400],
                          fontSize: 12,
                        ),
                      ),
                      const SizedBox(height: 4),
                      Text(
                        agent.styleSummary,
                        maxLines: 2,
                        overflow:
                            TextOverflow.ellipsis,
                        style: const TextStyle(
                          fontSize: 13,
                        ),
                      ),
                    ],
                  ),
                  isThreeLine: true,
                  trailing: const Icon(
                    Icons.chevron_right,
                  ),
                  onTap: () {
                    context.go(
                      '/agents/'
                      '${agent.expertId}'
                      '/chat'
                      '?name='
                      '${Uri.encodeComponent(agent.expertName)}',
                    );
                  },
                ),
              );
            },
          );
        },
      ),
    );
  }

  void _showError(String message) {
    WidgetsBinding.instance.addPostFrameCallback(
      (_) {
        if (!mounted) return;
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(message),
            backgroundColor: Colors.red,
          ),
        );
      },
    );
  }
}
