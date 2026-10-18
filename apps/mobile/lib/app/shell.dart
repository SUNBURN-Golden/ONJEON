import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

import '../design/tokens.g.dart';
import '../session/app_session.dart';
import 'routes.dart';

/// Banner shown on every screen while the example mode is on. The data behind it is
/// synthetic (`synthetic=true`) and the wording says it is not a quote.
class SyntheticBanner extends StatelessWidget {
  const SyntheticBanner({super.key});

  @override
  Widget build(BuildContext context) {
    final session = SessionScope.of(context);
    if (!session.synthetic) return const SizedBox.shrink();
    return Container(
      key: const Key('synthetic-banner'),
      width: double.infinity,
      color: OnjeonColors.segSelected,
      padding: const EdgeInsets.symmetric(
        horizontal: OnjeonDimension.gutter,
        vertical: OnjeonSpace.xs,
      ),
      child: Row(
        children: [
          Expanded(
            child: Semantics(
              label: '예시 모드. synthetic=true. 화면 예시이며 실제 견적이 아닙니다',
              excludeSemantics: true,
              child: const Wrap(
                spacing: OnjeonSpace.md,
                children: [
                  Text('화면 예시 · 실제 견적 아님', style: OnjeonText.rowSubtitle),
                  Text('synthetic=true', key: Key('synthetic-flag'), style: OnjeonText.caption),
                ],
              ),
            ),
          ),
          TextButton(
            onPressed: session.endExample,
            child: Text(
              '예시 끝내기',
              style: OnjeonText.caption.copyWith(color: OnjeonColors.accentText),
            ),
          ),
        ],
      ),
    );
  }
}

/// Four tabs. Switching keeps each tab's own state (section 4.8 of the screen spec).
class AppShell extends StatelessWidget {
  const AppShell({super.key, required this.shell});

  final StatefulNavigationShell shell;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: OnjeonColors.bg,
      body: SafeArea(
        bottom: false,
        child: Column(
          children: [
            const SyntheticBanner(),
            Expanded(child: shell),
          ],
        ),
      ),
      bottomNavigationBar: DecoratedBox(
        decoration: const BoxDecoration(
          color: OnjeonColors.bg,
          border: Border(top: BorderSide(color: OnjeonColors.tabbarBorder)),
        ),
        child: SafeArea(
          child: SizedBox(
            height: OnjeonDimension.tabbarHeight,
            child: Row(
              children: [
                for (var i = 0; i < appTabs.length; i++)
                  Expanded(
                    child: _TabItem(
                      tab: appTabs[i],
                      selected: shell.currentIndex == i,
                      onTap: () => shell.goBranch(i, initialLocation: i == shell.currentIndex),
                    ),
                  ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _TabItem extends StatelessWidget {
  const _TabItem({required this.tab, required this.selected, required this.onTap});

  final TabSpec tab;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final color = selected ? OnjeonColors.tabSelected : OnjeonColors.tabUnselected;
    return Semantics(
      button: true,
      selected: selected,
      label: tab.label,
      excludeSemantics: true,
      child: InkWell(
        key: Key('tab-${tab.path.substring(1)}'),
        onTap: onTap,
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(tab.icon, color: color, size: 24),
            const SizedBox(height: OnjeonSpace.xs),
            Text(
              tab.label,
              style: OnjeonText.tabLabel.copyWith(
                color: color,
                fontWeight: selected ? FontWeight.w700 : FontWeight.w400,
              ),
            ),
          ],
        ),
      ),
    );
  }
}
