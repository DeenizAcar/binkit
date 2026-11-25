import 'package:bink_it/features/credits/credits_screen.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  test('parseCredits skips comments and malformed lines', () {
    final credits = parseCredits('''
# header
Jane Doe | CC BY 4.0 | https://commons.wikimedia.org/?curid=123
broken line
Unknown | Public domain | https://commons.wikimedia.org/?curid=456
''');
    expect(credits.map((c) => c.author), ['Jane Doe', 'Unknown']);
    expect(credits.first.license, 'CC BY 4.0');
  });
}
