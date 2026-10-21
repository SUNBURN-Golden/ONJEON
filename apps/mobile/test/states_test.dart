import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:onjeon_contracts/onjeon_contracts.dart';
import 'package:onjeon_mobile/design/tokens.g.dart';
import 'package:onjeon_mobile/states/frames.dart';
import 'package:onjeon_mobile/states/screen_state.dart';

import 'support/pump_app.dart';

const _content = Text('마지막 결과', key: Key('content'));

void main() {
  test('the common states are exactly the seven of Part 3 section 44.2', () {
    expect(ScreenState.values.map((s) => s.name), [
      'loading', 'empty', 'partial', 'undecidable', 'stale', 'error', 'changed', //
    ]);
  });

  testWidgets('every state has its own frame', (tester) async {
    const keys = {
      ScreenState.loading: 'state-loading',
      ScreenState.empty: 'state-empty',
      ScreenState.partial: 'state-partial',
      ScreenState.undecidable: 'state-undecidable',
      ScreenState.stale: 'state-stale',
      ScreenState.error: 'state-error',
      ScreenState.changed: 'state-changed',
    };
    for (final s in ScreenState.values) {
      await tester.pumpWidget(framed(ScreenStateFrame(state: s, content: _content, args: const FrameArgs(question: '질문?'))));
      expect(find.byKey(Key(keys[s]!)), findsOneWidget, reason: s.name);
      // A frame shows exactly one state.
      for (final other in keys.entries.where((e) => e.key != s)) {
        expect(find.byKey(Key(other.value)), findsNothing, reason: '${s.name} vs ${other.key.name}');
      }
    }
  });

  group('loading', () {
    testWidgets('skeleton first, sentence only after 2 seconds', (tester) async {
      await tester.pumpWidget(framed(const LoadingFrame()));
      expect(find.byKey(const Key('loading-slow')), findsNothing);
      await tester.pump(const Duration(milliseconds: 1999));
      expect(find.byKey(const Key('loading-slow')), findsNothing);
      await tester.pump(const Duration(milliseconds: 2));
      expect(find.byKey(const Key('loading-slow')), findsOneWidget);
    });

    testWidgets('disposing before the timer fires is quiet', (tester) async {
      await tester.pumpWidget(framed(const LoadingFrame()));
      await tester.pumpWidget(framed(const SizedBox()));
      await tester.pump(const Duration(seconds: 3));
    });
  });

  group('empty', () {
    testWidgets('shows the holdings status and keeps 가입내역 없이 보기', (tester) async {
      var taps = 0;
      await tester.pumpWidget(framed(EmptyFrame(
        holdings: PolicyHoldingsStatus.skipped,
        onBrowseWithoutHoldings: () => taps++,
      )));
      expect(find.text('가입내역을 아직 올리지 않았어요'), findsOneWidget);
      await tester.tap(find.text('가입내역 없이 보기'));
      expect(taps, 1);
    });

    test('every holdings status has its own sentence (none is read as zero insurance)', () {
      final lines = PolicyHoldingsStatus.values.map(holdingsLine).toSet();
      expect(lines.length, PolicyHoldingsStatus.values.length);
      expect(holdingsLine(PolicyHoldingsStatus.unknown), contains('없는 것으로 보지 않아요'));
      expect(holdingsLine(PolicyHoldingsStatus.noneDeclared), contains('본인 답변'));
    });
  });

  testWidgets('partial: known content, 확인 필요 n건, no total', (tester) async {
    await tester.pumpWidget(framed(const PartialFrame(unresolvedCount: 3, child: _content)));
    expect(find.text('확인 필요 3건'), findsOneWidget);
    expect(find.byKey(const Key('content')), findsOneWidget);
    expect(find.textContaining('합계'), findsNothing);
  });

  testWidgets('undecidable: one question and no large figure', (tester) async {
    await tester.pumpWidget(framed(const UndecidableFrame(question: '진단받은 시점이 언제인가요?', rangeText: '범위로만 볼 수 있어요')));
    expect(find.byKey(const Key('undecidable-question')), findsOneWidget);
    final sizes = tester.widgetList<Text>(find.byType(Text)).map((t) => t.style?.fontSize ?? 0);
    expect(sizes.every((s) => s < OnjeonText.figure.fontSize!), isTrue);
  });

  testWidgets('stale: warning band and the unchanged result', (tester) async {
    await tester.pumpWidget(framed(const StaleFrame(asOf: '10-01', child: _content)));
    expect(find.textContaining('최신 정보가 아닐 수 있어요'), findsOneWidget);
    expect(find.textContaining('10-01'), findsOneWidget);
    expect(find.byKey(const Key('content')), findsOneWidget);
  });

  group('error', () {
    testWidgets('last result, failure fact and retry', (tester) async {
      var retries = 0;
      await tester.pumpWidget(framed(ErrorFrame(onRetry: () => retries++, lastResult: _content)));
      expect(find.text('마지막으로 확인한 결과예요'), findsOneWidget);
      expect(find.text('새로 불러오지 못했어요'), findsOneWidget);
      expect(find.byKey(const Key('content')), findsOneWidget);
      await tester.tap(find.text('다시 시도'));
      expect(retries, 1);
    });

    testWidgets('without a last result it does not invent one', (tester) async {
      await tester.pumpWidget(framed(ErrorFrame(onRetry: () {})));
      expect(find.text('마지막으로 확인한 결과예요'), findsNothing);
      expect(find.text('새로 불러오지 못했어요'), findsOneWidget);
    });

    testWidgets('no retry callback disables the button instead of a dead tap', (tester) async {
      await tester.pumpWidget(framed(const ErrorFrame(onRetry: null)));
      expect(tester.widget<FilledButton>(find.byType(FilledButton)).onPressed, isNull);
    });
  });

  testWidgets('changed: before, after and the cause', (tester) async {
    for (final c in ChangeCause.values) {
      await tester.pumpWidget(framed(ChangedFrame(cause: c, before: '이전 문장', after: '이후 문장')));
      expect(find.text(c.label), findsOneWidget);
      expect(find.text('이전 문장'), findsOneWidget);
      expect(find.text('이후 문장'), findsOneWidget);
    }
    expect(ChangeCause.values.map((c) => c.label).toSet().length, 2);
  });

  testWidgets('frames fit a 360px width at large text without overflow', (tester) async {
    tester.view.physicalSize = const Size(360, 780);
    tester.view.devicePixelRatio = 1.0;
    tester.platformDispatcher.textScaleFactorTestValue = 1.6;
    addTearDown(() {
      tester.view.reset();
      tester.platformDispatcher.clearTextScaleFactorTestValue();
    });
    for (final s in ScreenState.values) {
      await tester.pumpWidget(framed(ScreenStateFrame(
        state: s,
        content: _content,
        args: FrameArgs(question: '진단받은 시점이 언제인가요? 아주 긴 질문 문장이 두 줄 이상으로 넘어가도 괜찮은지 봅니다', unresolvedCount: 12, onRetry: () {}, before: '이전', after: '이후'),
      )));
      expect(tester.takeException(), isNull, reason: s.name);
    }
  });
}
