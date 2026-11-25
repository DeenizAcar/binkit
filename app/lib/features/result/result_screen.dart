import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:image/image.dart' as img;
import 'package:intl/intl.dart';

import '../../data/price_repository.dart';
import '../../l10n/app_localizations.dart';
import '../scanner/scan_pipeline.dart';

/// Vehicle card for a successful scan.
///
/// Shows the plate-masked frame only. The brand is shown as text, never
/// as a logo.
class ResultScreen extends StatefulWidget {
  const ResultScreen({super.key, required this.result, this.price});

  final ScanSuccess result;
  final PriceRange? price;

  @override
  State<ResultScreen> createState() => _ResultScreenState();
}

class _ResultScreenState extends State<ResultScreen> {
  late final Uint8List _jpeg =
      img.encodeJpg(widget.result.maskedFrame, quality: 85);

  @override
  Widget build(BuildContext context) {
    final l10n = AppLocalizations.of(context);
    final theme = Theme.of(context);
    final scheme = theme.colorScheme;
    final result = widget.result;
    final others = result.predictions.skip(1).toList();

    return Scaffold(
      appBar: AppBar(title: Text(l10n.resultTitle)),
      body: SafeArea(
        child: ListView(
          padding: const EdgeInsets.all(16),
          children: [
            ClipRRect(
              borderRadius: BorderRadius.circular(16),
              child: AspectRatio(
                aspectRatio: 4 / 3,
                child: Image.memory(_jpeg, fit: BoxFit.cover, gaplessPlayback: true),
              ),
            ),
            const SizedBox(height: 16),
            Card(
              child: Padding(
                padding: const EdgeInsets.all(20),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      result.top.label.toUpperCase(),
                      style: theme.textTheme.headlineLarge?.copyWith(
                        fontWeight: FontWeight.w900,
                        letterSpacing: 2,
                      ),
                    ),
                    const SizedBox(height: 8),
                    _ConfidenceBar(value: result.top.confidence),
                    const SizedBox(height: 4),
                    Text(
                      l10n.confidence((result.top.confidence * 100).round()),
                      style: theme.textTheme.bodyMedium
                          ?.copyWith(color: scheme.onSurfaceVariant),
                    ),
                    const Divider(height: 32),
                    // No toUpperCase() on translated text: Dart's casing is
                    // not locale-aware (Turkish i → I instead of İ).
                    Text(l10n.estimatedValue,
                        style: theme.textTheme.labelLarge
                            ?.copyWith(color: scheme.primary, letterSpacing: 1.5)),
                    const SizedBox(height: 6),
                    Text(
                      _formatPrice(context, widget.price) ?? l10n.priceUnavailable,
                      style: theme.textTheme.headlineSmall
                          ?.copyWith(fontWeight: FontWeight.w800),
                    ),
                    if (widget.price != null) ...[
                      const SizedBox(height: 4),
                      Text(l10n.priceDisclaimer,
                          style: theme.textTheme.bodySmall
                              ?.copyWith(color: scheme.onSurfaceVariant)),
                    ],
                  ],
                ),
              ),
            ),
            if (others.isNotEmpty) ...[
              const SizedBox(height: 16),
              Text(l10n.otherGuesses, style: theme.textTheme.titleMedium),
              const SizedBox(height: 8),
              for (final p in others)
                ListTile(
                  contentPadding: EdgeInsets.zero,
                  title: Text(p.label),
                  trailing: Text(l10n.confidence((p.confidence * 100).round())),
                ),
            ],
            const SizedBox(height: 24),
            FilledButton.icon(
              onPressed: () => Navigator.of(context).pop(),
              icon: const Icon(Icons.center_focus_strong),
              label: Text(l10n.scanAgain),
            ),
            const SizedBox(height: 12),
            Text(
              l10n.privacyNote,
              textAlign: TextAlign.center,
              style: theme.textTheme.bodySmall
                  ?.copyWith(color: scheme.onSurfaceVariant),
            ),
          ],
        ),
      ),
    );
  }

  String? _formatPrice(BuildContext context, PriceRange? price) {
    if (price == null) return null;
    final format = NumberFormat.simpleCurrency(
      locale: Localizations.localeOf(context).toString(),
      name: price.currency,
      decimalDigits: 0,
    );
    return '${format.format(price.min)} – ${format.format(price.max)}';
  }
}

class _ConfidenceBar extends StatelessWidget {
  const _ConfidenceBar({required this.value});

  final double value;

  @override
  Widget build(BuildContext context) {
    return ClipRRect(
      borderRadius: BorderRadius.circular(4),
      child: LinearProgressIndicator(value: value, minHeight: 8),
    );
  }
}
