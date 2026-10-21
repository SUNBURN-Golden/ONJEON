// Round trip of every fixture through the generated Dart classes.
// Run by codegen/build_check.sh against a scratch copy of generated/dart:
//   dart run bin/roundtrip.dart <fixtures dir>
import 'dart:convert';
import 'dart:io';

import 'package:onjeon_contracts/onjeon_contracts.dart';

Map<String, dynamic> Function(Map<String, dynamic>) codec(String type) {
  switch (type) {
    case 'Assertion':
      return (j) => Assertion.fromJson(j).toJson();
    case 'ReleaseManifest':
      return (j) => ReleaseManifest.fromJson(j).toJson();
    case 'EvaluationResult':
      return (j) => EvaluationResult.fromJson(j).toJson();
    case 'ScenarioResult':
      return (j) => ScenarioResult.fromJson(j).toJson();
    case 'CoverageDetail':
      return (j) => CoverageDetail.fromJson(j).toJson();
    case 'CompareView':
      return (j) => CompareView.fromJson(j).toJson();
    case 'PlanView':
      return (j) => PlanView.fromJson(j).toJson();
    case 'EvidenceView':
      return (j) => EvidenceView.fromJson(j).toJson();
    case 'NeedResult':
      return (j) => NeedResult.fromJson(j).toJson();
    case 'PremiumObservation':
      return (j) => PremiumObservation.fromJson(j).toJson();
    case 'ContractSnapshot':
      return (j) => ContractSnapshot.fromJson(j).toJson();
    case 'ErrorResponse':
      return (j) => ErrorResponse.fromJson(j).toJson();
  }
  throw StateError('no codec for $type');
}

bool same(Object? a, Object? b) {
  if (a is Map && b is Map) {
    return a.length == b.length &&
        a.keys.every((k) => b.containsKey(k) && same(a[k], b[k]));
  }
  if (a is List && b is List) {
    if (a.length != b.length) return false;
    for (var i = 0; i < a.length; i++) {
      if (!same(a[i], b[i])) return false;
    }
    return true;
  }
  return a == b;
}

void main(List<String> args) {
  final dir = Directory(args.first);
  final files = dir
      .listSync()
      .whereType<File>()
      .where((f) => f.path.endsWith('.fixture.json'))
      .toList()
    ..sort((a, b) => a.path.compareTo(b.path));
  var failed = 0;
  for (final f in files) {
    final name = f.uri.pathSegments.last;
    final type = name.split('.').first;
    final original = jsonDecode(f.readAsStringSync()) as Map<String, dynamic>;
    final back = codec(type)(original);
    if (same(back, original)) {
      print('ok   $name');
    } else {
      print('FAIL $name: round trip changed the document');
      failed++;
    }
  }
  // unknown vocabulary values are errors, never defaults
  final bad = jsonDecode(
          File('${args.first}/Assertion.relation.fixture.json').readAsStringSync())
      as Map<String, dynamic>;
  bad['criticality'] = 'c9';
  try {
    Assertion.fromJson(bad);
    print('FAIL unknown criticality was accepted');
    failed++;
  } on FormatException {
    print('ok   unknown criticality rejected');
  }
  final missing = jsonDecode(
          File('${args.first}/Assertion.relation.fixture.json').readAsStringSync())
      as Map<String, dynamic>;
  missing.remove('evidence');
  try {
    Assertion.fromJson(missing);
    print('FAIL missing required field was accepted');
    failed++;
  } catch (_) {
    print('ok   missing required field rejected');
  }
  if (failed > 0) exit(1);
}
