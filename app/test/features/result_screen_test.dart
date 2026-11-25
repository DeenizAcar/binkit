import 'package:bink_it/app.dart';
import 'package:bink_it/data/price_repository.dart';
import 'package:bink_it/features/result/result_screen.dart';
import 'package:bink_it/features/scanner/scan_pipeline.dart';
import 'package:bink_it/l10n/app_localizations.dart';
import 'package:bink_it/ml/car_classifier.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:image/image.dart' as img;

Widget wrap(Widget child, {Locale locale = const Locale('en')}) => MaterialApp(
      theme: BinkItApp.theme(),
      locale: locale,
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      supportedLocales: AppLocalizations.supportedLocales,
      home: child,
    );

final success = ScanSuccess(
  maskedFrame: img.Image(width: 8, height: 6),
  predictions: const [
    CarPrediction('Toyota', 0.87),
    CarPrediction('Honda', 0.08),
  ],
);

void usePhoneSize(WidgetTester tester) {
  tester.view.physicalSize = const Size(1080, 2400);
  tester.view.devicePixelRatio = 3;
  addTearDown(tester.view.reset);
}

void main() {
  testWidgets('shows brand as text, confidence and other guesses',
      (tester) async {
    usePhoneSize(tester);
    await tester.pumpWidget(wrap(ResultScreen(result: success)));
    await tester.pumpAndSettle();

    expect(find.text('TOYOTA'), findsOneWidget);
    expect(find.text('87% match'), findsOneWidget);
    expect(find.text('Honda'), findsOneWidget);
    expect(find.text('No price data yet'), findsOneWidget);
  });

  testWidgets('shows price range when available, in Turkish', (tester) async {
    usePhoneSize(tester);
    await tester.pumpWidget(wrap(
      ResultScreen(
        result: success,
        price: const PriceRange(min: 8000, max: 45000, currency: 'USD'),
      ),
      locale: const Locale('tr'),
    ));
    await tester.pumpAndSettle();

    expect(find.text('Tahmini değer'), findsOneWidget);
    expect(find.textContaining('8.000'), findsOneWidget);
    expect(find.text('Tekrar tara'), findsOneWidget);
  });
}
