import 'package:flutter/material.dart';

import '../app/routes.dart';
import '../design/tokens.g.dart';
import '../session/app_session.dart';
import '../states/frames.dart';
import 'screen_page.dart';

class MeScreen extends StatelessWidget {
  const MeScreen({super.key});

  @override
  Widget build(BuildContext context) {
    final session = SessionScope.of(context);
    Widget row(String title, String subtitle) => Container(
          padding: const EdgeInsets.symmetric(vertical: OnjeonSpace.lg),
          decoration: const BoxDecoration(
            border: Border(bottom: BorderSide(color: OnjeonColors.divider)),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(title, style: OnjeonText.rowTitle),
              const SizedBox(height: OnjeonSpace.xs),
              Text(subtitle, style: OnjeonText.rowSubtitle),
            ],
          ),
        );
    return ScreenPage(
      title: appTabs[3].label,
      subtitle: appTabs[3].question,
      body: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          row('프로필', '본인과 가족'),
          row('가입내역', holdingsLine(session.holdings)),
          row('동의·권한', '처리 동의와 삭제'),
          const SizedBox(height: OnjeonSpace.lg),
          const NotConnectedNotice(what: '프로필·가입내역·동의 관리'),
        ],
      ),
    );
  }
}
