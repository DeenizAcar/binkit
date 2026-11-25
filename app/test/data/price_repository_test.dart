import 'package:bink_it/data/price_repository.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('parses ranges, case-insensitive lookup, currency override', () {
    final repo = PriceRepository.fromJson('''
      {
        "version": 1,
        "currency": "USD",
        "brands": {
          "Toyota": {"min": 8000, "max": 45000},
          "Skoda": {"min": 7000, "max": 30000, "currency": "EUR"},
          "Broken": {"min": 50, "max": 10}
        }
      }
    ''');

    final toyota = repo.forBrand('toyota')!;
    expect(toyota.min, 8000);
    expect(toyota.currency, 'USD');
    expect(repo.forBrand('Skoda')!.currency, 'EUR');
    expect(repo.forBrand('Broken'), isNull, reason: 'max < min is rejected');
    expect(repo.forBrand('Unknown'), isNull);
  });

  test('empty brands map is valid', () {
    final repo = PriceRepository.fromJson('{"version":1,"brands":{}}');
    expect(repo.forBrand('Toyota'), isNull);
  });
}
