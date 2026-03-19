import 'package:flutter/material.dart';
import 'package:flutter_svg/flutter_svg.dart';
import 'package:go_router/go_router.dart';
import 'package:march_madness/core/theme/app_theme.dart';
import 'package:march_madness/features/auth/login_screen.dart';
import 'package:march_madness/features/auth/signup_screen.dart';
import 'package:march_madness/features/bracket/bracket_screen.dart';
import 'package:march_madness/features/experts/expert_picks_screen.dart';
import 'package:march_madness/features/agents/agent_list_screen.dart';
import 'package:march_madness/features/agents/agent_chat_screen.dart';
import 'package:march_madness/features/agents/bracket_rating_screen.dart';

// ── Colors shared with bracket styling ────────────────────────────────────────
const _kNavBg       = Color(0xFFFFFFFF);
const _kHeaderBg    = Color(0xFFFFFFFF);
const _kDivider     = Color(0xFFD0D0D0);
const _kOrange      = Color(0xFFFF6D00);
const _kTextDark    = Color(0xFF333333);
const _kTextMuted   = Color(0xFF757575);

final _rootNavKey = GlobalKey<NavigatorState>();
final _shellNavKey = GlobalKey<NavigatorState>();

final _router = GoRouter(
  navigatorKey: _rootNavKey,
  initialLocation: '/login',
  routes: [
    GoRoute(
      path: '/login',
      builder: (context, state) => const LoginScreen(),
    ),
    GoRoute(
      path: '/signup',
      builder: (context, state) => const SignupScreen(),
    ),
    StatefulShellRoute.indexedStack(
      builder: (context, state, navigationShell) {
        return _ShellScaffold(navigationShell: navigationShell);
      },
      branches: [
        StatefulShellBranch(
          routes: [
            GoRoute(
              path: '/bracket',
              builder: (context, state) => const BracketScreen(),
            ),
          ],
        ),
        StatefulShellBranch(
          routes: [
            GoRoute(
              path: '/experts',
              builder: (context, state) => const ExpertPicksScreen(),
            ),
          ],
        ),
        StatefulShellBranch(
          navigatorKey: _shellNavKey,
          routes: [
            GoRoute(
              path: '/agents',
              builder: (context, state) => const AgentListScreen(),
              routes: [
                GoRoute(
                  path: ':id/chat',
                  parentNavigatorKey: _rootNavKey,
                  builder: (context, state) {
                    final id = state.pathParameters['id']!;
                    final name =
                        state.uri.queryParameters['name'] ?? id;
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
              builder: (context, state) => const BracketRatingScreen(),
            ),
          ],
        ),
      ],
    ),
  ],
);

// ── Shell scaffold ─────────────────────────────────────────────────────────────

class _ShellScaffold extends StatelessWidget {
  final StatefulNavigationShell navigationShell;
  const _ShellScaffold({required this.navigationShell});

  void _onTap(int i) => navigationShell.goBranch(
        i,
        initialLocation: i == navigationShell.currentIndex,
      );

  @override
  Widget build(BuildContext context) {
    final wide = MediaQuery.sizeOf(context).width >= 600;
    return wide ? _wideLayout(context) : _narrowLayout(context);
  }

  // ── Desktop ──────────────────────────────────────────────────────────────────

  Widget _wideLayout(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFFF5F5F5),
      body: Column(
        children: [
          _TopHeader(),
          const Divider(height: 1, thickness: 1, color: _kDivider),
          Expanded(
            child: Row(
              children: [
                _SideNav(
                  selectedIndex: navigationShell.currentIndex,
                  onDestinationSelected: _onTap,
                ),
                const VerticalDivider(
                    thickness: 1, width: 1, color: _kDivider),
                Expanded(child: navigationShell),
              ],
            ),
          ),
        ],
      ),
    );
  }

  // ── Mobile ───────────────────────────────────────────────────────────────────

  Widget _narrowLayout(BuildContext context) {
    return Scaffold(
      appBar: _buildAppBar(),
      body: navigationShell,
      bottomNavigationBar: _buildBottomNav(),
    );
  }

  PreferredSizeWidget _buildAppBar() {
    return PreferredSize(
      preferredSize: const Size.fromHeight(56),
      child: Container(
        color: _kHeaderBg,
        child: Column(
          mainAxisAlignment: MainAxisAlignment.end,
          children: [
            SizedBox(
              height: 55,
              child: Center(
                child: SvgPicture.asset(
                  'assets/march_madness_logo.svg',
                  height: 28,
                  fit: BoxFit.contain,
                ),
              ),
            ),
            const Divider(height: 1, thickness: 1, color: _kDivider),
          ],
        ),
      ),
    );
  }

  BottomNavigationBar _buildBottomNav() {
    return BottomNavigationBar(
      currentIndex: navigationShell.currentIndex,
      onTap: _onTap,
      type: BottomNavigationBarType.fixed,
      backgroundColor: _kNavBg,
      selectedItemColor: _kOrange,
      unselectedItemColor: _kTextMuted,
      selectedLabelStyle: const TextStyle(
        fontWeight: FontWeight.w800,
        fontSize: 10,
        letterSpacing: 0.8,
      ),
      unselectedLabelStyle: const TextStyle(
        fontWeight: FontWeight.w600,
        fontSize: 10,
        letterSpacing: 0.8,
      ),
      elevation: 0,
      items: const [
        BottomNavigationBarItem(
          icon: Icon(Icons.sports_basketball),
          label: 'BRACKET',
        ),
        BottomNavigationBarItem(
          icon: Icon(Icons.people),
          label: 'EXPERTS',
        ),
        BottomNavigationBarItem(
          icon: Icon(Icons.chat),
          label: 'CHAT',
        ),
        BottomNavigationBarItem(
          icon: Icon(Icons.star_rate),
          label: 'RATE',
        ),
      ],
    );
  }
}

// ── Top header with logo ───────────────────────────────────────────────────────

class _TopHeader extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    return Container(
      height: 56,
      color: _kHeaderBg,
      padding: const EdgeInsets.symmetric(horizontal: 20),
      child: Center(
        child: SvgPicture.asset(
          'assets/march_madness_logo.svg',
          height: 30,
          fit: BoxFit.contain,
        ),
      ),
    );
  }
}

// ── Side navigation rail ───────────────────────────────────────────────────────

class _SideNav extends StatelessWidget {
  final int selectedIndex;
  final ValueChanged<int> onDestinationSelected;

  const _SideNav({
    required this.selectedIndex,
    required this.onDestinationSelected,
  });

  static const _destinations = [
    NavigationRailDestination(
      icon: Icon(Icons.sports_basketball_outlined),
      selectedIcon: Icon(Icons.sports_basketball),
      label: Text('BRACKET'),
    ),
    NavigationRailDestination(
      icon: Icon(Icons.people_outline),
      selectedIcon: Icon(Icons.people),
      label: Text('EXPERTS'),
    ),
    NavigationRailDestination(
      icon: Icon(Icons.chat_bubble_outline),
      selectedIcon: Icon(Icons.chat_bubble),
      label: Text('CHAT'),
    ),
    NavigationRailDestination(
      icon: Icon(Icons.star_outline),
      selectedIcon: Icon(Icons.star),
      label: Text('RATE'),
    ),
  ];

  @override
  Widget build(BuildContext context) {
    return Theme(
      data: Theme.of(context).copyWith(
        navigationRailTheme: NavigationRailThemeData(
          backgroundColor: _kNavBg,
          selectedIconTheme: const IconThemeData(color: _kOrange, size: 22),
          unselectedIconTheme:
              const IconThemeData(color: _kTextMuted, size: 22),
          selectedLabelTextStyle: const TextStyle(
            color: _kOrange,
            fontSize: 10,
            fontWeight: FontWeight.w800,
            letterSpacing: 1.2,
          ),
          unselectedLabelTextStyle: const TextStyle(
            color: _kTextMuted,
            fontSize: 10,
            fontWeight: FontWeight.w600,
            letterSpacing: 1.2,
          ),
          indicatorColor: Color(0x1AFF6D00), // orange at 10% opacity
          indicatorShape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(4),
          ),
          useIndicator: true,
          minWidth: 80,
        ),
      ),
      child: NavigationRail(
        selectedIndex: selectedIndex,
        onDestinationSelected: onDestinationSelected,
        labelType: NavigationRailLabelType.all,
        destinations: _destinations,
      ),
    );
  }
}

// ── Root app ───────────────────────────────────────────────────────────────────

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
