import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:onjeon_mobile/app/routes.dart';
import 'package:onjeon_mobile/design/theme.dart';
import 'package:onjeon_mobile/session/app_session.dart';
import 'package:onjeon_mobile/states/frames.dart';

import 'support/pump_app.dart';

Color _textColor(WidgetTester tester, Finder text) =>
    tester.renderObject<RenderParagraph>(text).text.style!.color!;

Color _buttonBackground(WidgetTester tester, Finder button) {
  final surface = find.descendant(of: button, matching: find.byType(Material));
  return tester.widget<Material>(surface).color!;
}

void _expectContrast(Color foreground, Color background, double minimum) {
  final first = foreground.computeLuminance();
  final second = background.computeLuminance();
  final ratio =
      (math.max(first, second) + 0.05) / (math.min(first, second) + 0.05);
  expect(
    ratio,
    greaterThanOrEqualTo(minimum),
    reason: '$foreground on $background',
  );
}

void _expectScaledLabelFits(WidgetTester tester, Finder text, Finder control) {
  final paragraph = tester.renderObject<RenderParagraph>(text);
  final size = paragraph.text.style!.fontSize!;
  expect(paragraph.textScaler.scale(size), size * 2);
  final length = paragraph.text.toPlainText().length;
  final glyphs = paragraph.getBoxesForSelection(
    TextSelection(baseOffset: 0, extentOffset: length),
  );
  expect(
    paragraph.getBoxesForSelection(
      TextSelection(baseOffset: length - 1, extentOffset: length),
    ),
    isNotEmpty,
    reason: 'The final glyph must be laid out',
  );
  // Selection metrics can overhang the render box by a fraction of a pixel.
  final labelBounds = (Offset.zero & paragraph.size).inflate(1);
  for (final line in glyphs) {
    expect(
      labelBounds.contains(line.toRect().topLeft),
      isTrue,
      reason: '$text',
    );
    expect(
      labelBounds.contains(line.toRect().bottomRight),
      isTrue,
      reason: '$text',
    );
  }
  final textRect = tester.getRect(text);
  final controlRect = tester.getRect(control).inflate(0.01);
  expect(
    controlRect.contains(textRect.topLeft),
    isTrue,
    reason: '$text clips at the top left',
  );
  expect(
    controlRect.contains(textRect.bottomRight),
    isTrue,
    reason: '$text clips at the bottom right',
  );
  expect(control.hitTestable(), findsOneWidget);
}

void main() {
  testWidgets('entry buttons and heading meet text and control contrast', (
    tester,
  ) async {
    await pumpApp(tester);
    final pageBackground = tester
        .widget<Scaffold>(find.byType(Scaffold))
        .backgroundColor!;
    final startExample = find.byKey(const Key('entry-example'));
    _expectContrast(
      _textColor(tester, find.text(EntryPoint.example.label)),
      _buttonBackground(tester, startExample),
      4.5,
    );
    final freshButton = tester.widget<OutlinedButton>(
      find.byKey(const Key('entry-fresh')),
    );
    _expectContrast(
      _textColor(tester, find.text(EntryPoint.fresh.label)),
      pageBackground,
      4.5,
    );
    _expectContrast(
      freshButton.style!.side!.resolve({})!.color,
      pageBackground,
      3,
    );
    _expectContrast(
      _textColor(tester, find.text('내 보험, 직접 이해하세요')),
      pageBackground,
      3,
    );
  });

  testWidgets('example banner text and exit button meet contrast', (
    tester,
  ) async {
    await pumpApp(
      tester,
      location: AppPaths.home,
      session: AppSession()..enter(EntryPoint.example),
    );
    final banner = tester.widget<Container>(
      find.byKey(const Key('synthetic-banner')),
    );
    _expectContrast(
      _textColor(tester, find.text('예시 끝내기')),
      banner.color!,
      4.5,
    );
    _expectContrast(
      _textColor(tester, find.text('화면 예시 · 실제 견적 아님')),
      banner.color!,
      4.5,
    );
  });

  testWidgets('partial status text and frame button meet contrast', (
    tester,
  ) async {
    await tester.pumpWidget(
      MaterialApp(
        theme: buildTheme(),
        home: Scaffold(
          body: PartialFrame(
            unresolvedCount: 2,
            child: ErrorFrame(onRetry: () {}),
          ),
        ),
      ),
    );
    final page = tester.widget<Scaffold>(find.byType(Scaffold));
    final background =
        page.backgroundColor ??
        Theme.of(tester.element(find.byType(Scaffold))).scaffoldBackgroundColor;
    _expectContrast(_textColor(tester, find.text('확인 필요 2건')), background, 4.5);
    final retry = find.byType(FilledButton);
    _expectContrast(
      _textColor(
        tester,
        find.descendant(of: retry, matching: find.byType(Text)),
      ),
      _buttonBackground(tester, retry),
      4.5,
    );
  });

  testWidgets(
    'tabs expose names, selected state and working screen-reader actions',
    (tester) async {
      await pumpApp(
        tester,
        location: AppPaths.home,
        session: AppSession()..enter(EntryPoint.fresh),
      );

      final tabs = [
        for (final tab in appTabs)
          find.semantics.byPredicate(
            (node) =>
                node.label == tab.label &&
                node.getSemanticsData().flagsCollection.isButton,
          ),
      ];
      for (var step = 1; step <= tabs.length; step++) {
        final selected = step % tabs.length;
        tester.semantics.tap(tabs[selected]);
        await tester.pumpAndSettle();
        for (var index = 0; index < tabs.length; index++) {
          expect(
            tabs[index].evaluate().single,
            isSemantics(
              isButton: true,
              hasTapAction: true,
              isSelected: index == selected,
            ),
            reason: appTabs[index].label,
          );
        }
        expect(find.text(appTabs[selected].question), findsOneWidget);
      }
    },
  );

  testWidgets('entry heading and choices follow the visible reading order', (
    tester,
  ) async {
    await pumpApp(tester);
    expect(
      tester.semantics.simulatedAccessibilityTraversal(),
      containsAllInOrder([
        isSemantics(label: '내 보험, 직접 이해하세요', isHeader: true),
        isSemantics(label: '가입내역이나 건강 정보 없이도 시작할 수 있어요.'),
        for (final entry in EntryPoint.values)
          isSemantics(label: entry.label, isButton: true, hasTapAction: true),
      ]),
    );
  });

  testWidgets(
    'entry, banner and all four tabs fit and work at 360 px and 200% text',
    (tester) async {
      await pumpApp(tester, size: const Size(360, 740), textScale: 2);
      for (final entry in EntryPoint.values) {
        final control = find.byKey(Key('entry-${entry.name}'));
        await tester.ensureVisible(control);
        await tester.pumpAndSettle();
        _expectScaledLabelFits(tester, find.text(entry.label), control);
      }
      final example = find.byKey(const Key('entry-example'));
      await tester.ensureVisible(example);
      await tester.tap(example);
      await tester.pumpAndSettle();

      final endExample = find.widgetWithText(TextButton, '예시 끝내기');
      _expectScaledLabelFits(tester, find.text('예시 끝내기'), endExample);
      for (final tab in appTabs) {
        final control = find.byKey(Key('tab-${tab.path.substring(1)}'));
        final label = find.descendant(
          of: control,
          matching: find.text(tab.label),
        );
        _expectScaledLabelFits(tester, label, control);
        await tester.tap(control);
        await tester.pumpAndSettle();
        expect(find.text(tab.question), findsOneWidget);
        expect(tester.takeException(), isNull, reason: tab.label);
      }
      await tester.tap(endExample);
      await tester.pumpAndSettle();
      expect(find.byKey(const Key('synthetic-banner')), findsNothing);
    },
  );
}
