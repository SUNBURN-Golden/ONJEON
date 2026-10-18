import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

import '../design/theme.dart';
import '../session/app_session.dart';
import 'router.dart';
import 'shell.dart';
import 'routes.dart';

class OnjeonApp extends StatefulWidget {
  const OnjeonApp({super.key, this.initialLocation = AppPaths.entry, this.session});

  final String initialLocation;

  /// Injected by tests; a fresh session otherwise.
  final AppSession? session;

  @override
  State<OnjeonApp> createState() => _OnjeonAppState();
}

class _OnjeonAppState extends State<OnjeonApp> {
  late final AppSession _session = widget.session ?? AppSession();
  late final GoRouter _router = buildRouter(initialLocation: widget.initialLocation);

  @override
  void dispose() {
    _router.dispose();
    if (widget.session == null) _session.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return SessionScope(
      session: _session,
      child: MaterialApp.router(
        title: '온전',
        theme: buildTheme(),
        routerConfig: _router,
        builder: (context, child) => SyntheticFrame(child: child ?? const SizedBox.shrink()),
        debugShowCheckedModeBanner: false,
      ),
    );
  }
}
