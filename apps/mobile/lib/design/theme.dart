import 'package:flutter/material.dart';

import 'tokens.g.dart';

ThemeData buildTheme() {
  return ThemeData(
    useMaterial3: true,
    scaffoldBackgroundColor: OnjeonColors.bg,
    dividerColor: OnjeonColors.divider,
    colorScheme: ColorScheme.fromSeed(
      seedColor: OnjeonColors.accent,
      primary: OnjeonColors.accent,
      surface: OnjeonColors.bg,
    ),
  );
}
