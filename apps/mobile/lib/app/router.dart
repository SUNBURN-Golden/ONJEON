import 'package:go_router/go_router.dart';

import '../screens/entry_screen.dart';
import '../screens/evidence_screen.dart';
import '../screens/home_screen.dart';
import '../screens/me_screen.dart';
import '../screens/my_design_screen.dart';
import '../screens/not_found_screen.dart';
import '../screens/what_if_screen.dart';
import 'routes.dart';
import 'shell.dart';

GoRouter buildRouter({String initialLocation = AppPaths.entry}) {
  return GoRouter(
    initialLocation: initialLocation,
    errorBuilder: (context, state) => const NotFoundScreen(),
    routes: [
      GoRoute(
        path: AppPaths.entry,
        builder: (context, state) => const EntryScreen(),
      ),
      StatefulShellRoute.indexedStack(
        builder: (context, state, shell) => AppShell(shell: shell),
        branches: [
          StatefulShellBranch(routes: [
            GoRoute(path: AppPaths.home, builder: (c, s) => const HomeScreen()),
          ]),
          StatefulShellBranch(routes: [
            GoRoute(path: AppPaths.whatIf, builder: (c, s) => const WhatIfScreen()),
          ]),
          StatefulShellBranch(routes: [
            GoRoute(path: AppPaths.myDesign, builder: (c, s) => const MyDesignScreen()),
          ]),
          StatefulShellBranch(routes: [
            GoRoute(path: AppPaths.me, builder: (c, s) => const MeScreen()),
          ]),
        ],
      ),
      GoRoute(
        path: AppPaths.evidencePattern,
        builder: (context, state) =>
            EvidenceScreen(ref: state.pathParameters['ref'] ?? ''),
      ),
    ],
  );
}
