import 'package:flutter/material.dart';
import 'package:onjeon_contracts/onjeon_contracts.dart';

import '../design/tokens.g.dart';
import '../session/app_session.dart';
import '../states/frames.dart';
import '../states/screen_state.dart';

/// Common page layout: logo row, headline, then the body in the screen gutter. Scrolls, so a
/// 360px width or large text never hides the body.
class ScreenPage extends StatelessWidget {
  const ScreenPage({super.key, required this.title, this.subtitle, required this.body});

  final String title;
  final String? subtitle;
  final Widget body;

  @override
  Widget build(BuildContext context) {
    return SingleChildScrollView(
      padding: const EdgeInsets.fromLTRB(
        OnjeonDimension.gutter,
        OnjeonSpace.lg,
        OnjeonDimension.gutter,
        OnjeonSpace.xl,
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text('온전', style: OnjeonText.logo),
          const SizedBox(height: OnjeonSpace.xl),
          Text(title, style: OnjeonText.headline),
          if (subtitle != null) ...[
            const SizedBox(height: OnjeonSpace.sm),
            Text(subtitle!, style: OnjeonText.subhead),
          ],
          const SizedBox(height: OnjeonSpace.xl),
          body,
        ],
      ),
    );
  }
}

/// Said plainly on a screen whose data is not connected yet; never a fake value.
class NotConnectedNotice extends StatelessWidget {
  const NotConnectedNotice({super.key, required this.what});

  final String what;

  @override
  Widget build(BuildContext context) {
    return Container(
      key: const Key('not-connected'),
      width: double.infinity,
      padding: const EdgeInsets.all(OnjeonSpace.lg),
      decoration: BoxDecoration(
        border: Border.all(color: OnjeonColors.divider),
        borderRadius: BorderRadius.circular(OnjeonSpace.md),
      ),
      child: Text('$what은 아직 연결되지 않았어요.', style: OnjeonText.rowSubtitle),
    );
  }
}

/// Empty state until the user chooses to browse without holdings, then [child].
/// Holdings confirmed by the user skip the gate.
class HoldingsGate extends StatefulWidget {
  const HoldingsGate({super.key, required this.emptyMessage, required this.child});

  final String emptyMessage;
  final Widget child;

  @override
  State<HoldingsGate> createState() => _HoldingsGateState();
}

class _HoldingsGateState extends State<HoldingsGate> {
  bool _browsing = false;

  @override
  Widget build(BuildContext context) {
    final holdings = SessionScope.of(context).holdings;
    if (_browsing || holdings == PolicyHoldingsStatus.confirmed) return widget.child;
    return ScreenStateFrame(
      state: ScreenState.empty,
      args: FrameArgs(
        holdings: holdings,
        emptyMessage: widget.emptyMessage,
        onBrowseWithoutHoldings: () => setState(() => _browsing = true),
      ),
    );
  }
}
