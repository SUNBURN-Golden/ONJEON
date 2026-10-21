import 'package:flutter/material.dart';

import '../design/tokens.g.dart';
import 'entry_points.dart';
import 'screen_page.dart';

class EntryScreen extends StatelessWidget {
  const EntryScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return const Scaffold(
      backgroundColor: OnjeonColors.bg,
      body: SafeArea(
        child: ScreenPage(
          title: '내 보험, 직접 이해하세요',
          subtitle: '가입내역이나 건강 정보 없이도 시작할 수 있어요.',
          body: EntryPoints(),
        ),
      ),
    );
  }
}
