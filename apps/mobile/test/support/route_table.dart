import 'package:go_router/go_router.dart';

/// Every path the router registers, nested ones joined, as a deep link or tab could reach it.
List<String> registeredPaths(GoRouter router) {
  final out = <String>[];
  void walk(List<RouteBase> routes, String prefix) {
    for (final r in routes) {
      if (r is GoRoute) {
        final full = r.path.startsWith('/') ? r.path : '$prefix/${r.path}';
        out.add(full);
        walk(r.routes, full);
      } else if (r is StatefulShellRoute) {
        for (final b in r.branches) {
          walk(b.routes, prefix);
        }
      } else {
        walk(r.routes, prefix);
      }
    }
  }

  walk(router.configuration.routes, '');
  return out;
}
