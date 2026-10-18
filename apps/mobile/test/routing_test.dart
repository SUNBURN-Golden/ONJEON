import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:onjeon_mobile/app/routes.dart';
import 'package:onjeon_mobile/session/app_session.dart';

import 'support/pump_app.dart';

void main() {
  test('four tabs in the order of Part 3 section 44.1', () {
    expect(appTabs.map((t) => t.label), ['홈', '만약에', '내 설계', '내 정보']);
    expect(appTabs.map((t) => t.path), ['/home', '/what-if', '/my-design', '/me']);
  });

  test('three entry points, by name', () {
    expect(EntryPoint.values.map((e) => e.label), ['예시로 둘러보기', '처음부터 준비하기', '가입내역 PDF 올리기']);
  });

  group('entry points', () {
    testWidgets('first run shows all three and nothing else is required', (tester) async {
      await pumpApp(tester);
      for (final e in EntryPoint.values) {
        expect(find.byKey(Key('entry-${e.name}')), findsOneWidget);
      }
      // No consent, sign-in, PDF or consultation step is offered before the choice.
      expect(find.textContaining('동의'), findsNothing);
      expect(find.textContaining('로그인'), findsNothing);
      expect(find.textContaining('상담'), findsNothing);
    });

    testWidgets('예시로 둘러보기 opens 홈 in example mode', (tester) async {
      final s = await pumpApp(tester);
      await tester.tap(find.byKey(const Key('entry-example')));
      await tester.pumpAndSettle();
      expect(s.synthetic, isTrue);
      expect(find.byKey(const Key('tab-home')), findsOneWidget);
      expect(find.byKey(const Key('synthetic-banner')), findsOneWidget);
    });

    testWidgets('처음부터 준비하기 opens 홈 without the banner', (tester) async {
      final s = await pumpApp(tester);
      await tester.tap(find.byKey(const Key('entry-fresh')));
      await tester.pumpAndSettle();
      expect(s.entry, EntryPoint.fresh);
      expect(s.synthetic, isFalse);
      expect(find.byKey(const Key('synthetic-banner')), findsNothing);
      expect(find.byKey(const Key('tab-home')), findsOneWidget);
    });

    testWidgets('가입내역 PDF 올리기 goes to 내 정보 and does not claim holdings', (tester) async {
      final s = await pumpApp(tester);
      await tester.tap(find.byKey(const Key('entry-pdf')));
      await tester.pumpAndSettle();
      expect(s.entry, EntryPoint.pdf);
      expect(find.text('내 정보'), findsWidgets);
      expect(find.text('가입내역을 아직 올리지 않았어요'), findsOneWidget);
    });

    testWidgets('홈 offers the entry points when none was chosen, and hides them after', (tester) async {
      await pumpApp(tester, location: AppPaths.home);
      expect(find.byKey(const Key('entry-points')), findsOneWidget);
      await tester.tap(find.byKey(const Key('entry-fresh')));
      await tester.pumpAndSettle();
      expect(find.byKey(const Key('entry-points')), findsNothing);
    });
  });

  group('tabs', () {
    testWidgets('each tab opens its screen', (tester) async {
      await pumpApp(tester, location: AppPaths.home);
      const titles = {
        'tab-home': '홈',
        'tab-what-if': '만약에',
        'tab-my-design': '나에게 필요한 만큼',
        'tab-me': '내 정보',
      };
      for (final e in titles.entries) {
        await tester.tap(find.byKey(Key(e.key)));
        await tester.pumpAndSettle();
        expect(find.descendant(of: find.byType(Scaffold).first, matching: find.text(e.value)), findsWidgets, reason: e.key);
      }
    });

    testWidgets('switching tabs keeps the state of the tab left behind', (tester) async {
      await pumpApp(tester, location: AppPaths.home);
      await tester.tap(find.byKey(const Key('entry-fresh')));
      await tester.pumpAndSettle();
      await tester.tap(find.text('가입내역 없이 보기'));
      await tester.pumpAndSettle();
      expect(find.byKey(const Key('not-connected')), findsOneWidget);
      await tester.tap(find.byKey(const Key('tab-me')));
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const Key('tab-home')));
      await tester.pumpAndSettle();
      expect(find.byKey(const Key('not-connected')), findsOneWidget);
    });

    testWidgets('내 설계 and 홈 start in the empty state with the holdings status', (tester) async {
      await pumpApp(tester, location: AppPaths.myDesign);
      expect(find.byKey(const Key('state-empty')), findsOneWidget);
      expect(find.text('가입내역을 아직 올리지 않았어요'), findsOneWidget);
      expect(find.text('가입내역 없이 보기'), findsOneWidget);
    });

    testWidgets('만약에 asks one question instead of showing an amount', (tester) async {
      await pumpApp(tester, location: AppPaths.whatIf);
      expect(find.byKey(const Key('state-undecidable')), findsOneWidget);
      expect(find.byKey(const Key('undecidable-question')), findsOneWidget);
    });
  });

  group('evidence', () {
    testWidgets('is reachable by link with no entry choice, PDF, consent or consultation', (tester) async {
      await pumpApp(tester, location: AppPaths.evidence('clause-1'));
      expect(find.text('증거 보기'), findsOneWidget);
      expect(find.byKey(const Key('evidence-ref')), findsOneWidget);
      expect(find.textContaining('동의'), findsNothing);
    });

    testWidgets('back without history goes to 홈', (tester) async {
      await pumpApp(tester, location: AppPaths.evidence('clause-1'));
      await tester.tap(find.byType(BackButton));
      await tester.pumpAndSettle();
      expect(find.byKey(const Key('tab-home')), findsOneWidget);
    });

    test('a reference with a slash stays one path segment', () {
      expect(AppPaths.evidence('a/b c'), '/evidence/a%2Fb%20c');
    });
  });

  group('example mode', () {
    testWidgets('banner shows the wording and synthetic=true on every tab', (tester) async {
      final session = AppSession()..enter(EntryPoint.example);
      await pumpApp(tester, location: AppPaths.home, session: session);
      for (final key in ['tab-home', 'tab-what-if', 'tab-my-design', 'tab-me']) {
        await tester.tap(find.byKey(Key(key)));
        await tester.pumpAndSettle();
        expect(find.text('화면 예시 · 실제 견적 아님'), findsOneWidget, reason: key);
        expect(find.text('synthetic=true'), findsOneWidget, reason: key);
      }
    });

    testWidgets('banner is also on the first-run screen once example mode is on', (tester) async {
      final session = AppSession()..enter(EntryPoint.example);
      await pumpApp(tester, location: AppPaths.entry, session: session);
      expect(find.byKey(const Key('synthetic-flag')), findsOneWidget);
    });

    testWidgets('banner is absent outside example mode', (tester) async {
      await pumpApp(tester, location: AppPaths.home, session: AppSession()..enter(EntryPoint.fresh));
      expect(find.byKey(const Key('synthetic-banner')), findsNothing);
      expect(find.textContaining('synthetic'), findsNothing);
    });

    testWidgets('예시 끝내기 removes the banner', (tester) async {
      final session = AppSession()..enter(EntryPoint.example);
      await pumpApp(tester, location: AppPaths.home, session: session);
      await tester.tap(find.text('예시 끝내기'));
      await tester.pumpAndSettle();
      expect(session.synthetic, isFalse);
      expect(find.byKey(const Key('synthetic-banner')), findsNothing);
    });

    testWidgets('the banner carries a semantics label with synthetic=true', (tester) async {
      final session = AppSession()..enter(EntryPoint.example);
      await pumpApp(tester, location: AppPaths.home, session: session);
      final node = find.byWidgetPredicate(
        (w) => w is Semantics && (w.properties.label ?? '').contains('synthetic=true'),
      );
      expect(node, findsOneWidget);
    });
  });

  group('layout', () {
    testWidgets('every tab fits 360px at 1.6x text', (tester) async {
      await pumpApp(tester, location: AppPaths.home, size: const Size(360, 740), textScale: 1.6);
      for (final key in ['tab-home', 'tab-what-if', 'tab-my-design', 'tab-me']) {
        await tester.tap(find.byKey(Key(key)));
        await tester.pumpAndSettle();
        expect(tester.takeException(), isNull, reason: key);
      }
    });
  });
}
