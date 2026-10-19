import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:onjeon_mobile/app/router.dart';
import 'package:onjeon_mobile/app/routes.dart';

import 'support/pump_app.dart';
import 'support/route_table.dart';

const _flagsPath = '../../packages/schemas/feature_flags.json';

Map<String, dynamic> _flags() => jsonDecode(File(_flagsPath).readAsStringSync()) as Map<String, dynamic>;

List<Map<String, dynamic>> _flagList() => (_flags()['flags'] as List).cast<Map<String, dynamic>>();

String _bare(String p) => p.startsWith('/v1/') ? p.substring(3) : p;

/// Skeleton route paths of every flag, with and without the /v1 prefix.
Set<String> _skeletonPaths() {
  final out = <String>{};
  for (final f in _flagList()) {
    for (final r in (f['inactive_routes'] as List).cast<Map<String, dynamic>>()) {
      final p = r['path'] as String;
      out..add(p)..add(_bare(p));
    }
  }
  return out;
}

bool _exposes(String route, String skeleton) {
  final r = _bare(route);
  final s = _bare(skeleton);
  return r == s || r.startsWith('${s.endsWith('/') ? s.substring(0, s.length - 1) : s}/');
}

void main() {
  test('the flags file is the shipped one: every flag is off', () {
    final flags = _flagList();
    expect(flags, isNotEmpty);
    expect(flags.where((f) => f['default'] != false), isEmpty);
    expect(_skeletonPaths(), isNotEmpty, reason: 'nothing to check against');
  });

  test('no registered route exposes a skeleton path', () {
    final router = buildRouter();
    addTearDown(router.dispose);
    final paths = registeredPaths(router);
    expect(paths, containsAll(['/entry', '/home', '/what-if', '/my-design', '/me', '/evidence/:ref']));
    for (final route in paths) {
      for (final s in _skeletonPaths()) {
        expect(_exposes(route, s), isFalse, reason: '$route exposes $s');
      }
    }
  });

  test('no navigation entry points at a skeleton path', () {
    for (final tab in appTabs) {
      for (final s in _skeletonPaths()) {
        expect(_exposes(tab.path, s), isFalse, reason: '${tab.label} -> ${tab.path}');
      }
    }
  });

  test('the CI skeleton probe finds nothing in the registered routes (same rule as check_skeleton.py)', () async {
    final router = buildRouter();
    addTearDown(router.dispose);
    final dir = Directory.systemTemp.createTempSync('onj_routes_');
    addTearDown(() => dir.deleteSync(recursive: true));
    final routesFile = File('${dir.path}/routes.json')..writeAsStringSync(jsonEncode(registeredPaths(router)));
    const script = r'''
import json, sys
sys.path.insert(0, sys.argv[1])
import check_skeleton as S
import ci_common as C
flags = C.load_json(C.FLAGS_PATH)
routes = json.load(open(sys.argv[2], encoding="utf-8"))
found = [f.render() for f in S.probe_ui_routes(routes, flags)]
print(json.dumps({"routes": len(routes), "findings": found}))
''';
    final r = await Process.run('python3', ['-I', '-c', script, '../../tools/ci', routesFile.path]);
    expect(r.exitCode, 0, reason: '${r.stderr}');
    final out = jsonDecode((r.stdout as String).trim()) as Map<String, dynamic>;
    expect(out['routes'], greaterThanOrEqualTo(6));
    expect(out['findings'], isEmpty);
  });

  test('the probe rejects a planted skeleton route (it can fail)', () async {
    final planted = _skeletonPaths().first;
    const script = r'''
import json, sys
sys.path.insert(0, sys.argv[1])
import check_skeleton as S
import ci_common as C
flags = C.load_json(C.FLAGS_PATH)
print(len(S.probe_ui_routes(["/home", sys.argv[2], sys.argv[2] + "/new"], flags)))
''';
    final r = await Process.run('python3', ['-I', '-c', script, '../../tools/ci', planted]);
    expect(r.exitCode, 0, reason: '${r.stderr}');
    expect((r.stdout as String).trim(), '2');
  });

  test('app code never names a skeleton flag, feature or route', () {
    final needles = <String>{..._skeletonPaths()};
    for (final f in _flagList()) {
      needles..add(f['id'] as String)..add(f['feature'] as String);
    }
    final files = Directory('lib').listSync(recursive: true).whereType<File>().where((f) => f.path.endsWith('.dart'));
    expect(files, isNotEmpty);
    for (final f in files) {
      final text = f.readAsStringSync();
      for (final n in needles) {
        expect(text.contains(n), isFalse, reason: '${f.path} contains "$n"');
      }
    }
  });

  // Paths come from the flags file, so the list cannot drift from the contract.
  group('deep links to disabled surfaces land on not-found, with no tab bar', () {
    final paths = <String>{
      for (final p in _skeletonPaths()) ...[p, '$p/child'],
      '/consultation',
    };
    for (final path in paths) {
      testWidgets(path, (tester) async {
        await pumpApp(tester, location: path);
        expect(find.text('찾을 수 없는 화면이에요'), findsOneWidget);
        expect(find.byKey(const Key('tab-home')), findsNothing);
      });
    }
  });
}
