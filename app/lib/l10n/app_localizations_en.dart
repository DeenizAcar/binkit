// ignore: unused_import
import 'package:intl/intl.dart' as intl;
import 'app_localizations.dart';

// ignore_for_file: type=lint

/// The translations for English (`en`).
class AppLocalizationsEn extends AppLocalizations {
  AppLocalizationsEn([String locale = 'en']) : super(locale);

  @override
  String get appTitle => 'Bink It';

  @override
  String get scanButton => 'Scan';

  @override
  String get scanning => 'Scanning…';

  @override
  String get loadingCamera => 'Starting camera…';

  @override
  String get cameraPermissionDenied =>
      'Camera access is needed to scan cars. Allow it in your phone\'s settings.';

  @override
  String get cameraUnavailable => 'Camera not available on this device.';

  @override
  String get tryAgain => 'Try again';

  @override
  String get aimHint => 'Fit the whole car in the frame';

  @override
  String get plateTooLarge => 'Capture the whole car';

  @override
  String get plateTooLargeHint =>
      'The license plate takes up too much of the frame. Step back.';

  @override
  String get uncertain => 'Not sure, try again';

  @override
  String get uncertainHint => 'Try a clearer angle with the whole car in view.';

  @override
  String get modelsUnavailable => 'Recognition models aren\'t installed yet.';

  @override
  String get scanFailed => 'Something went wrong. Try again.';

  @override
  String get resultTitle => 'Scan result';

  @override
  String confidence(int percent) {
    return '$percent% match';
  }

  @override
  String get otherGuesses => 'Other guesses';

  @override
  String get estimatedValue => 'Estimated value';

  @override
  String get priceUnavailable => 'No price data yet';

  @override
  String get priceDisclaimer =>
      'Rough range for typical used cars. Not an appraisal.';

  @override
  String get scanAgain => 'Scan again';

  @override
  String get privacyNote =>
      'Plates are masked on your device. Nothing is saved or sent.';
}
