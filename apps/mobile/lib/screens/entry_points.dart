import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

import '../app/routes.dart';
import '../design/tokens.g.dart';
import '../session/app_session.dart';

/// The three entry points. Used on the first-run screen and at the top of 홈 when the user
/// has not chosen one. Choosing one sends nothing and requires no PDF, family history,
/// consent or consultation.
class EntryPoints extends StatelessWidget {
  const EntryPoints({super.key});

  static String _target(EntryPoint e) =>
      e == EntryPoint.pdf ? AppPaths.me : AppPaths.home;

  @override
  Widget build(BuildContext context) {
    final session = SessionScope.of(context);
    return Column(
      key: const Key('entry-points'),
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        for (final e in EntryPoint.values) ...[
          SizedBox(
            height: OnjeonDimension.buttonHeight,
            child: e == EntryPoint.example
                ? FilledButton(
                    key: Key('entry-${e.name}'),
                    style: FilledButton.styleFrom(
                      backgroundColor: OnjeonColors.accent,
                      shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(OnjeonDimension.buttonRadius),
                      ),
                    ),
                    onPressed: () {
                      session.enter(e);
                      context.go(_target(e));
                    },
                    child: Text(e.label, style: OnjeonText.button),
                  )
                : OutlinedButton(
                    key: Key('entry-${e.name}'),
                    style: OutlinedButton.styleFrom(
                      side: const BorderSide(color: OnjeonColors.accent),
                      shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(OnjeonDimension.buttonRadius),
                      ),
                    ),
                    onPressed: () {
                      session.enter(e);
                      context.go(_target(e));
                    },
                    child: Text(
                      e.label,
                      style: OnjeonText.button.copyWith(color: OnjeonColors.accentText),
                    ),
                  ),
          ),
          const SizedBox(height: OnjeonSpace.md),
        ],
      ],
    );
  }
}
