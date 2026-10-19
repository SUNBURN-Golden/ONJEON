import 'package:flutter/material.dart';

import '../app/routes.dart';
import 'screen_page.dart';

class MyDesignScreen extends StatelessWidget {
  const MyDesignScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return ScreenPage(
      title: '나에게 필요한 만큼',
      subtitle: appTabs[2].question,
      body: const HoldingsGate(
        emptyMessage: '현재 계약을 아직 확인하지 않았어요. 관심 담보 기준으로 비교를 이어갈 수 있어요.',
        child: NotConnectedNotice(what: '필요 담보와 비교'),
      ),
    );
  }
}
