import '../../config/scan_config.dart';
import '../../data/price_repository.dart';
import '../../ml/car_classifier.dart';
import '../../ml/plate_detector.dart';
import 'scan_pipeline.dart';

/// Loads models and data once for the scanner.
class ScanServices {
  ScanServices({required this.pipeline, required this.prices});

  final ScanPipeline pipeline;
  final PriceRepository prices;

  static Future<ScanServices> load({ScanConfig config = const ScanConfig()}) async {
    final results = await Future.wait([
      TfLitePlateDetector.tryLoad(),
      TfLiteCarClassifier.tryLoad(),
      PriceRepository.loadFromAssets(),
    ]);
    return ScanServices(
      pipeline: ScanPipeline(
        detector: results[0] as PlateDetector?,
        classifier: results[1] as CarClassifier?,
        config: config,
      ),
      prices: results[2] as PriceRepository,
    );
  }

  void dispose() => pipeline.close();
}
