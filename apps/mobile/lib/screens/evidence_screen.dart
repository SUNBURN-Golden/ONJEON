import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

import '../app/routes.dart';
import '../design/tokens.g.dart';
import 'screen_page.dart';

/// Common evidence view (Part 3 section 44.1). Reachable by link from any screen without a
/// PDF, family history or consultation.
class EvidenceScreen extends StatelessWidget {
  const EvidenceScreen({super.key, required this.ref});

  final String ref;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: OnjeonColors.bg,
      appBar: AppBar(
        backgroundColor: OnjeonColors.bg,
        leading: BackButton(
          onPressed: () => context.canPop() ? context.pop() : context.go(AppPaths.home),
        ),
      ),
      body: SafeArea(
        child: ScreenPage(
          title: '증거 보기',
          subtitle: '이 숫자는 어디서 왔나요?',
          body: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text('근거 $ref', key: const Key('evidence-ref'), style: OnjeonText.caption),
              const SizedBox(height: OnjeonSpace.md),
              const NotConnectedNotice(what: '원문 페이지·조항·버전'),
            ],
          ),
        ),
      ),
    );
  }
}
