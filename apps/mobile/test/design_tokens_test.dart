import 'dart:convert';
import 'dart:io';

import 'package:flutter/painting.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:onjeon_mobile/design/tokens.g.dart';

Map<String, dynamic> _tokens() =>
    jsonDecode(File('../../packages/design-tokens/tokens.json').readAsStringSync()) as Map<String, dynamic>;

int _rgb(String hex) => 0xFF000000 | int.parse(hex.substring(1), radix: 16);

void main() {
  test('core colours are the measured values of the design spec', () {
    expect(OnjeonColors.bg.toARGB32(), _rgb('#F6F4EE'));
    expect(OnjeonColors.accent.toARGB32(), _rgb('#AE583F'));
    expect(OnjeonColors.accentText.toARGB32(), _rgb('#A14529'));
    expect(OnjeonColors.ink.toARGB32(), _rgb('#1A1411'));
    expect(OnjeonColors.ink2.toARGB32(), _rgb('#66554A'));
    expect(OnjeonColors.divider.toARGB32(), _rgb('#E3DED5'));
  });

  test('generated Dart agrees with tokens.json for sizes and weights', () {
    final t = _tokens();
    final text = t['text'] as Map<String, dynamic>;
    expect(OnjeonText.headline.fontSize, (text['headline'] as Map)['size']);
    expect(OnjeonText.figure.fontSize, (text['figure'] as Map)['size']);
    expect(OnjeonText.figure.fontWeight, FontWeight.w800);
    expect(OnjeonText.logo.fontWeight, FontWeight.w700);
    expect(OnjeonDimension.referenceWidth, 390);
    expect(OnjeonDimension.referenceHeight, 844);
    expect(OnjeonDimension.minWidth, 360);
    expect(OnjeonDimension.rowPitch, 73);
  });

  test('the Dart colour set has exactly the colours of the JSON', () {
    final src = File('lib/design/tokens.g.dart').readAsStringSync();
    final declared = RegExp(r'static const Color (\w+) =').allMatches(src).length;
    expect(declared, (_tokens()['color'] as Map).length);
  });
}
