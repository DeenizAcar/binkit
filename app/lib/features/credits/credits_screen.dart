import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../l10n/app_localizations.dart';

/// One attribution line from image_credits.txt.
class PhotoCredit {
  const PhotoCredit({
    required this.author,
    required this.license,
    required this.url,
  });

  final String author;
  final String license;
  final String url;
}

/// Parses `author | license | url` lines; `#` lines are comments.
///
/// File titles are deliberately not included: many Commons titles contain
/// license plate numbers.
List<PhotoCredit> parseCredits(String text) => [
      for (final line in text.split('\n'))
        if (line.trim().isNotEmpty && !line.trimLeft().startsWith('#'))
          if (line.split('|').map((s) => s.trim()).toList()
              case [final author, final license, final url])
            PhotoCredit(author: author, license: license, url: url),
    ];

/// Static attributions. Reads only a bundled asset; no network.
class CreditsScreen extends StatefulWidget {
  const CreditsScreen({super.key});

  static const asset = 'assets/data/image_credits.txt';

  @override
  State<CreditsScreen> createState() => _CreditsScreenState();
}

class _CreditsScreenState extends State<CreditsScreen> {
  late final Future<List<PhotoCredit>> _credits = rootBundle
      .loadString(CreditsScreen.asset)
      .then(parseCredits)
      .catchError((_) => <PhotoCredit>[]);

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    final theme = Theme.of(context);
    final muted = theme.textTheme.bodySmall
        ?.copyWith(color: theme.colorScheme.onSurfaceVariant);

    return Scaffold(
      appBar: AppBar(title: Text(l10n.creditsTitle)),
      body: FutureBuilder<List<PhotoCredit>>(
        future: _credits,
        builder: (context, snapshot) {
          final credits = snapshot.data ?? const <PhotoCredit>[];
          return ListView(
            padding: const EdgeInsets.all(16),
            children: [
              Text(l10n.creditsDataHeading, style: theme.textTheme.titleMedium),
              const SizedBox(height: 8),
              Text(l10n.creditsOpenImages),
              const SizedBox(height: 8),
              Text(l10n.creditsCommons),
              const SizedBox(height: 16),
              OutlinedButton(
                onPressed: () => showLicensePage(
                  context: context,
                  applicationName: l10n.appTitle,
                ),
                child: Text(l10n.creditsOpenSource),
              ),
              const Divider(height: 32),
              Text(l10n.creditsPhotosHeading, style: theme.textTheme.titleMedium),
              const SizedBox(height: 8),
              if (snapshot.connectionState != ConnectionState.done)
                const Center(child: CircularProgressIndicator())
              else if (credits.isEmpty)
                Text(l10n.creditsNoPhotos, style: muted)
              else
                for (final c in credits)
                  Padding(
                    padding: const EdgeInsets.symmetric(vertical: 4),
                    child: SelectableText(
                      '${c.author} (${c.license})\n${c.url}',
                      style: muted,
                    ),
                  ),
            ],
          );
        },
      ),
    );
  }
}
