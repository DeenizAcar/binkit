import 'package:flutter/material.dart';

import 'features/scanner/scanner_screen.dart';
import 'l10n/app_localizations.dart';

class BinkItApp extends StatelessWidget {
  const BinkItApp({super.key});

  static ThemeData theme() {
    final scheme = ColorScheme.fromSeed(
      seedColor: const Color(0xFF2EE6A6),
      brightness: Brightness.dark,
    );
    return ThemeData(
      colorScheme: scheme,
      scaffoldBackgroundColor: const Color(0xFF0D0F12),
      useMaterial3: true,
    );
  }

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      onGenerateTitle: (context) => AppLocalizations.of(context).appTitle,
      debugShowCheckedModeBanner: false,
      theme: theme(),
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      supportedLocales: AppLocalizations.supportedLocales,
      home: const ScannerScreen(),
    );
  }
}
