import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

import '../app/routes.dart';
import '../design/tokens.g.dart';
import 'screen_page.dart';

/// Any path the app does not register, including every disabled (skeleton) surface.
class NotFoundScreen extends StatelessWidget {
  const NotFoundScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: OnjeonColors.bg,
      body: SafeArea(
        child: ScreenPage(
          title: '찾을 수 없는 화면이에요',
          body: FilledButton(
            onPressed: () => context.go(AppPaths.home),
            child: const Text('홈으로'),
          ),
        ),
      ),
    );
  }
}
