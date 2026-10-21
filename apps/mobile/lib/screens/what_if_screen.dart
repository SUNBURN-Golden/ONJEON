import 'package:flutter/material.dart';

import '../app/routes.dart';
import '../states/frames.dart';
import '../states/screen_state.dart';
import 'screen_page.dart';

class WhatIfScreen extends StatelessWidget {
  const WhatIfScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return ScreenPage(
      title: appTabs[1].label,
      subtitle: '내가 가정한 상황에서 받을 수 있는 것을 봐요.',
      body: ScreenStateFrame(
        state: ScreenState.undecidable,
        args: FrameArgs(question: appTabs[1].question),
      ),
    );
  }
}
