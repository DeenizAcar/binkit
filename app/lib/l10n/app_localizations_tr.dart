// ignore: unused_import
import 'package:intl/intl.dart' as intl;
import 'app_localizations.dart';

// ignore_for_file: type=lint

/// The translations for Turkish (`tr`).
class AppLocalizationsTr extends AppLocalizations {
  AppLocalizationsTr([String locale = 'tr']) : super(locale);

  @override
  String get appTitle => 'Bink It';

  @override
  String get scanButton => 'Tara';

  @override
  String get scanning => 'Taranıyor…';

  @override
  String get loadingCamera => 'Kamera açılıyor…';

  @override
  String get cameraPermissionDenied =>
      'Araba taramak için kamera izni gerekli. Telefon ayarlarından izin ver.';

  @override
  String get cameraUnavailable => 'Bu cihazda kamera kullanılamıyor.';

  @override
  String get tryAgain => 'Tekrar dene';

  @override
  String get aimHint => 'Aracın tamamını kadraja al';

  @override
  String get plateTooLarge => 'Aracın tamamını çek';

  @override
  String get plateTooLargeHint =>
      'Plaka karenin çok büyük kısmını kaplıyor. Biraz geri çekil.';

  @override
  String get uncertain => 'Emin değilim, tekrar dene';

  @override
  String get uncertainHint =>
      'Aracın tamamı görünecek şekilde daha net bir açı dene.';

  @override
  String get modelsUnavailable => 'Tanıma modelleri henüz yüklü değil.';

  @override
  String get scanFailed => 'Bir şeyler ters gitti. Tekrar dene.';

  @override
  String get resultTitle => 'Tarama sonucu';

  @override
  String confidence(int percent) {
    return '%$percent eşleşme';
  }

  @override
  String get otherGuesses => 'Diğer tahminler';

  @override
  String get estimatedValue => 'Tahmini değer';

  @override
  String get priceUnavailable => 'Henüz fiyat verisi yok';

  @override
  String get priceDisclaimer =>
      'Tipik ikinci el araçlar için kaba bir aralık. Ekspertiz değildir.';

  @override
  String get scanAgain => 'Tekrar tara';

  @override
  String get privacyNote =>
      'Plakalar cihazında maskelenir. Hiçbir şey kaydedilmez veya gönderilmez.';

  @override
  String get creditsTitle => 'Emeği geçenler ve lisanslar';

  @override
  String get creditsDataHeading => 'Eğitim verisi';

  @override
  String get creditsOpenImages =>
      'Plaka tespiti, Google\'ın Open Images Dataset V7 verisiyle eğitildi. Etiketler: CC BY 4.0. Görseller: CC BY 2.0, Flickr\'daki sahiplerine ait.';

  @override
  String get creditsCommons =>
      'Araba tanıma kısmen Wikimedia Commons fotoğraflarıyla eğitildi (yalnızca kamu malı, CC0 ve CC BY). Fotoğrafçılar aşağıda listelenmiştir.';

  @override
  String get creditsOpenSource => 'Açık kaynak lisansları';

  @override
  String get creditsPhotosHeading => 'Fotoğraf kaynakları';

  @override
  String get creditsNoPhotos => 'Henüz fotoğraf kaynağı yok.';
}
