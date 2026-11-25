import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';

@immutable
class PriceRange {
  const PriceRange({
    required this.min,
    required this.max,
    required this.currency,
  });

  final num min;
  final num max;

  /// ISO 4217 code, e.g. "USD".
  final String currency;
}

/// Reads static price ranges bundled with the app. No network access.
///
/// assets/data/prices.json:
/// ```json
/// {
///   "version": 1,
///   "currency": "USD",
///   "brands": { "Toyota": { "min": 8000, "max": 45000 } }
/// }
/// ```
/// A brand may override the currency with its own "currency" field.
class PriceRepository {
  PriceRepository(Map<String, PriceRange> byBrand)
      : _byBrand = {
          for (final e in byBrand.entries) e.key.toLowerCase(): e.value,
        };

  static const asset = 'assets/data/prices.json';

  final Map<String, PriceRange> _byBrand;

  factory PriceRepository.fromJson(String source) {
    final json = jsonDecode(source) as Map<String, dynamic>;
    final defaultCurrency = (json['currency'] as String?) ?? 'USD';
    final brands = (json['brands'] as Map<String, dynamic>?) ?? const {};
    final ranges = <String, PriceRange>{};
    for (final entry in brands.entries) {
      final v = entry.value as Map<String, dynamic>;
      final min = v['min'] as num?;
      final max = v['max'] as num?;
      if (min == null || max == null || min < 0 || max < min) continue;
      ranges[entry.key] = PriceRange(
        min: min,
        max: max,
        currency: (v['currency'] as String?) ?? defaultCurrency,
      );
    }
    return PriceRepository(ranges);
  }

  static Future<PriceRepository> loadFromAssets() async {
    try {
      return PriceRepository.fromJson(await rootBundle.loadString(asset));
    } catch (e) {
      debugPrint('Price data unavailable: $e');
      return PriceRepository(const {});
    }
  }

  PriceRange? forBrand(String brand) => _byBrand[brand.toLowerCase()];
}
