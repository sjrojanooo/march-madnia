import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:march_madness/core/theme/app_theme.dart';
import 'package:march_madness/features/bracket/bracket_screen.dart';
import 'package:march_madness/features/experts/expert_picks_screen.dart';
import 'package:march_madness/features/agents/agent_list_screen.dart';
import 'package:march_madness/features/agents/agent_chat_screen.dart';
import 'package:march_madness/features/agents/bracket_rating_screen.dart';

final _rootNavKey = GlobalKey<NavigatorState>();
final _shellNavKey = GlobalKey<NavigatorState>();

final _router = GoRouter(
  navigatorKey: _rootNavKey,
  initialLocation: '/bracket',
  routes: [
    StatefulShellRoute.indexedStack(
      builder: (context, state, navigationShell) {
        return _ShellScaffold(navigationShell: navigationShell);
      },
      branches: [
        StatefulShellBranch(
          routes: [
            GoRoute(
              path: '/bracket',
              builder: (context, state) =>
                  const BracketScreen(),
            ),
          ],
        ),
        StatefulShellBranch(
          routes: [
            GoRoute(
              path: '/experts',
              builder: (context, state) =>
                  const ExpertPicksScreen(),
            ),
          ],
        ),
        StatefulShellBranch(
          navigatorKey: _shellNavKey,
          routes: [
            GoRoute(
              path: '/agents',
              builder: (context, state) =>
                  const AgentListScreen(),
              routes: [
                GoRoute(
                  path: ':id/chat',
                  parentNavigatorKey: _rootNavKey,
                  builder: (context, state) {
                    final id =
                        state.pathParameters['id']!;
                    final name =
                        state.uri.queryParameters[
                            'name'] ??
                            id;
                    return AgentChatScreen(
                      expertId: id,
                      expertName: name,
                    );
                  },
                ),
              ],
            ),
          ],
        ),
        StatefulShellBranch(
          routes: [
            GoRoute(
              path: '/rate',
              builder: (context, state) =>
                  const BracketRatingScreen(),
            ),
          ],
        ),
      ],
    ),
  ],
);

class _ShellScaffold extends StatelessWidget {
  final StatefulNavigationShell navigationShell;

  const _ShellScaffold({required this.navigationShell});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: navigationShell,
      bottomNavigationBar: BottomNavigationBar(
        currentIndex: navigationShell.currentIndex,
        onTap: (i) => navigationShell.goBranch(
          i,
          initialLocation:
              i == navigationShell.currentIndex,
        ),
        type: BottomNavigationBarType.fixed,
        items: const [
          BottomNavigationBarItem(
            icon: Icon(Icons.sports_basketball),
            label: 'Bracket',
          ),
          BottomNavigationBarItem(
            icon: Icon(Icons.people),
            label: 'Experts',
          ),
          BottomNavigationBarItem(
            icon: Icon(Icons.chat),
            label: 'Chat',
          ),
          BottomNavigationBarItem(
            icon: Icon(Icons.star_rate),
            label: 'Rate',
          ),
        ],
      ),
    );
  }
}

class MarchMadnessApp extends StatelessWidget {
  const MarchMadnessApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp.router(
      title: 'March Madness 2026',
      theme: AppTheme.dark,
      routerConfig: _router,
      debugShowCheckedModeBanner: false,
    );
  }
}
