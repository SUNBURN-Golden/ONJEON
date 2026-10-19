import 'package:flutter/material.dart';

import '../app/routes.dart';
import '../session/app_session.dart';
import 'entry_points.dart';
import 'screen_page.dart';

class HomeScreen extends StatelessWidget {
  const HomeScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final chosen = SessionScope.of(context).entry != null;
    return ScreenPage(
      title: appTabs[0].label,
      subtitle: appTabs[0].question,
      body: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          if (!chosen) const EntryPoints(),
          const HoldingsGate(
            emptyMessage: '가입내역 없이도 관심 담보의 보장과 못 받는 조건을 볼 수 있어요.',
            child: NotConnectedNotice(what: '담보 요약 목록'),
          ),
        ],
      ),
    );
  }
}
