import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

import '../tool/krw_lint.dart';

List<String> lint(String src) => lintSource('x.dart', src).map((f) => f.message).toList();

void main() {
  group('krw arithmetic is rejected', () {
    const bad = <String, String>{
      'addition': 'final t = a.insuredAmountKrw + b.insuredAmountKrw;',
      'addition on the right only': 'final t = 10 + row.krw;',
      'subtraction': 'final d = row.minKrw - row.maxKrw;',
      'multiplication': 'final d = row.krw * 12;',
      'division': 'final d = row.krw / 12;',
      'integer division': 'final d = row.krw ~/ 12;',
      'modulo': 'final d = row.krw % 1000;',
      'compound assignment': 'total += row.krw;',
      'negation': 'final d = -row.krw;',
      'increment': 'row.krw++;',
      'null-safe chain': 'final t = row?.price?.krw! + 1;',
      'indexed chain': 'final t = amounts[0].krw + amounts[1].krw;',
      'inside interpolation': r"final s = '${row.krw + 1}원';",
      'rounding': 'final r = row.krw.round();',
      'abs': 'final r = row.krw.abs();',
      'clamp': 'final r = row.krw.clamp(0, 10);',
      'toDouble': 'final r = row.krw.toDouble();',
      'fold': 'final t = rows.map((r) => r.krw).fold(0, (a, b) => a);',
      'reduce': 'final t = rows.map((r) => r.insuredAmountKrw).reduce((a, b) => a);',
      'alias then arithmetic': 'final v = row.krw;\nfinal t = v + 1;',
      'two-step alias': 'final v = row.krw;\nfinal w = v;\nfinal t = w * 2;',
      'camel and snake': 'final t = min_krw + maxKrw;',
    };
    bad.forEach((name, src) {
      test(name, () => expect(lint(src), isNotEmpty, reason: src));
    });

    test('line number is reported', () {
      final f = lintSource('screens/a.dart', 'void f() {\n  final t = a.krw + 1;\n}\n');
      expect(f.single.line, 2);
      expect(f.single.toString(), startsWith('screens/a.dart:2: KRW-ARITH'));
    });
  });

  group('allowed uses pass', () {
    const good = <String, String>{
      'pass through': r'Widget f(Row r) => Text(r.amountText, key: Key("${r.krw}"));',
      'comparison': 'final same = a.krw == b.krw; final big = a.krw > b.krw;',
      'null default': 'final v = row.krw ?? 0;',
      'ternary': 'final v = ok ? row.krw : null;',
      'argument list': 'show(a.krw, b.krw);',
      'comment arithmetic': '// total = a.krw + b.krw\nfinal x = 1;',
      'block comment': '/* a.krw * 2 */ final x = 1;',
      'string text': 'final s = "a.krw + b.krw";',
      'arithmetic on other names': 'final t = count + 1; final u = width * 2;',
      'url slash': "final u = 'https://x/y';",
      'word containing no krw': 'final t = karma + 1;',
    };
    good.forEach((name, src) {
      test(name, () => expect(lint(src), isEmpty, reason: src));
    });
  });

  test('screen code under lib has no amount arithmetic', () {
    final findings = lintTree(Directory('lib'));
    expect(findings.map((f) => f.toString()), isEmpty);
  });

  test('the lint covers every Dart file in lib (not an empty scan)', () {
    final n = Directory('lib').listSync(recursive: true).whereType<File>().where((f) => f.path.endsWith('.dart')).length;
    expect(n, greaterThan(10));
  });
}
