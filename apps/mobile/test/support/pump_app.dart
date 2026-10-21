import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:onjeon_mobile/app/app.dart';
import 'package:onjeon_mobile/session/app_session.dart';

/// Phone-sized surface (390x844) unless a test asks for another.
Future<AppSession> pumpApp(
  WidgetTester tester, {
  String? location,
  AppSession? session,
  Size size = const Size(390, 844),
  double textScale = 1.0,
}) async {
  tester.view.physicalSize = size;
  tester.view.devicePixelRatio = 1.0;
  tester.platformDispatcher.textScaleFactorTestValue = textScale;
  addTearDown(() {
    tester.view.reset();
    tester.platformDispatcher.clearTextScaleFactorTestValue();
  });
  final s = session ?? AppSession();
  await tester.pumpWidget(
    location == null ? OnjeonApp(session: s) : OnjeonApp(initialLocation: location, session: s),
  );
  await tester.pumpAndSettle();
  return s;
}

Widget framed(Widget child) => MaterialApp(home: Scaffold(body: SingleChildScrollView(child: child)));
