// Round trip of every API fixture through the generated Dart API classes.
// Run by codegen/build_check.sh against a scratch copy of generated/dart and generated/dart-api:
//   dart run bin/api_roundtrip.dart <api fixtures dir>
import 'dart:convert';
import 'dart:io';

import 'package:onjeon_api/onjeon_api.dart';

Map<String, dynamic> Function(Map<String, dynamic>) codec(String type) {
  switch (type) {
    case 'CurrentReleaseResponse':
      return (j) => CurrentReleaseResponse.fromJson(j).toJson();
    case 'ProductListResponse':
      return (j) => ProductListResponse.fromJson(j).toJson();
    case 'PolicyImportDetail':
      return (j) => PolicyImportDetail.fromJson(j).toJson();
    case 'EvaluationResponse':
      return (j) => EvaluationResponse.fromJson(j).toJson();
    case 'DeletionJobResponse':
      return (j) => DeletionJobResponse.fromJson(j).toJson();
    case 'ReleaseListResponse':
      return (j) => ReleaseListResponse.fromJson(j).toJson();
    case 'PolicyUpdateRequest':
      return (j) => PolicyUpdateRequest.fromJson(j).toJson();
    case 'ListProductsQuery':
      return (j) => ListProductsQuery.fromJson(j).toJson();
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
    final original = jsonDecode(f.readAsStringSync()) as Map<String, dynamic>;
    final back = codec(name.split('.').first)(original);
    if (same(back, original)) {
      print('ok   $name');
    } else {
      print('FAIL $name: round trip changed the document');
      failed++;
    }
  }
  // a response without release_id must not parse
  final noRelease = jsonDecode(
          File('${args.first}/CurrentReleaseResponse.fixture.json').readAsStringSync())
      as Map<String, dynamic>;
  noRelease.remove('release_id');
  try {
    CurrentReleaseResponse.fromJson(noRelease);
    print('FAIL a body without release_id was accepted');
    failed++;
  } catch (_) {
    print('ok   body without release_id rejected');
  }
  // unknown vocabulary values are errors, never defaults
  final bad = jsonDecode(
          File('${args.first}/ProductListResponse.fixture.json').readAsStringSync())
      as Map<String, dynamic>;
  (bad['items'] as List)[0]['sale_status'] = 'on_sale_maybe';
  try {
    ProductListResponse.fromJson(bad);
    print('FAIL unknown sale_status was accepted');
    failed++;
  } on FormatException {
    print('ok   unknown sale_status rejected');
  }
  // the default surface lists no skeleton operation
  if (operations.any((o) => o.skeleton || o.flag != null)) {
    print('FAIL default operations contain a skeleton operation');
    failed++;
  } else {
    print('ok   default operations contain no skeleton operation');
  }
  if (failed > 0) exit(1);
}
