import 'package:bink_it/features/credits/credits_screen.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('parseCredits skips comments and malformed lines', () {
    final credits = parseCredits('''
# header
File:Toyota Corolla.jpg | Jane Doe | CC BY 4.0 | https://commons.wikimedia.org/wiki/File:Toyota_Corolla.jpg
broken line
File:Old car.jpg | Unknown | Public domain | https://commons.wikimedia.org/wiki/File:Old_car.jpg
''');
    expect(credits.map((c) => c.author), ['Jane Doe', 'Unknown']);
    expect(credits.first.license, 'CC BY 4.0');
  });
}
