import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

/// The app has no transport of its own. Any HTTP call has to come from the generated
/// client (packages/schemas/codegen/generated), which has no transport yet, so lib/ must
/// contain no HTTP, socket or web-view machinery.
const _banned = <String, String>{
  'dart:io': 'dart:io (HttpClient, Socket)',
  'dart:html': 'dart:html (HttpRequest)',
  'dart:js': 'dart:js interop',
  'package:http/': 'package:http',
  'package:dio/': 'package:dio',
  'package:chopper/': 'package:chopper',
  'package:retrofit/': 'package:retrofit',
  'package:web_socket_channel/': 'web sockets',
  'package:webview_flutter/': 'web view',
  'package:url_launcher/': 'url launcher',
  'HttpClient': 'HttpClient',
  'XMLHttpRequest': 'XMLHttpRequest',
  'WebSocket': 'WebSocket',
  'Socket.connect': 'raw socket',
  'http://': 'http URL literal',
  'https://': 'https URL literal',
  'Uri.http': 'Uri.http',
  'Uri.https': 'Uri.https',
};

void main() {
  final files = Directory('lib').listSync(recursive: true).whereType<File>().where((f) => f.path.endsWith('.dart')).toList();

  test('lib has no HTTP, socket or URL-launching code', () {
    expect(files, isNotEmpty);
    for (final f in files) {
      final text = f.readAsStringSync();
      for (final e in _banned.entries) {
        expect(text.contains(e.key), isFalse, reason: '${f.path}: ${e.value}');
      }
    }
  });

  test('pubspec declares no HTTP package', () {
    final spec = File('pubspec.yaml').readAsStringSync();
    for (final p in ['http:', 'dio:', 'chopper:', 'retrofit:', 'web_socket_channel:', 'webview_flutter:', 'url_launcher:']) {
      expect(RegExp('^  $p', multiLine: true).hasMatch(spec), isFalse, reason: p);
    }
    expect(spec, contains('onjeon_contracts:'));
  });

  test('the check can fail: a planted call is found', () {
    const planted = "import 'dart:io';\nfinal c = HttpClient();\n";
    expect(_banned.keys.where(planted.contains), containsAll(['dart:io', 'HttpClient']));
  });
}
