import 'dart:math' as math;

import 'package:image/image.dart' as img;

import '../../config/scan_config.dart';
import '../../ml/car_classifier.dart';
import '../../ml/plate_detector.dart';
import '../../ml/plate_masker.dart';

sealed class ScanOutcome {
  const ScanOutcome();
}

/// Plate or classifier model is not installed. Nothing was classified:
/// without the plate detector a frame cannot be masked, so the pipeline
/// fails closed.
class ScanModelsUnavailable extends ScanOutcome {
  const ScanModelsUnavailable();
}

/// Plates cover too much of the frame ("Capture the whole car").
class ScanRejectedPlateTooLarge extends ScanOutcome {
  const ScanRejectedPlateTooLarge(this.plateAreaRatio);
  final double plateAreaRatio;
}

/// Top prediction is below the confidence threshold.
class ScanUncertain extends ScanOutcome {
  const ScanUncertain(this.predictions);
  final List<CarPrediction> predictions;
}

class ScanSuccess extends ScanOutcome {
  const ScanSuccess({required this.maskedFrame, required this.predictions});

  /// The frame with plates painted black. The only image that may leave
  /// the pipeline (e.g. for a result card).
  final img.Image maskedFrame;

  /// Best first, at most [ScanConfig.topK].
  final List<CarPrediction> predictions;

  CarPrediction get top => predictions.first;
}

/// Total plate area as a fraction of the frame (overlaps counted twice,
/// which only makes rejection stricter).
double plateAreaRatio(List<PlateBox> plates) =>
    math.min(1, plates.fold(0.0, (sum, p) => sum + p.area));

/// Frame → plate detection → reject/mask → classify → confidence gate.
class ScanPipeline {
  ScanPipeline({
    required this.detector,
    required this.classifier,
    this.config = const ScanConfig(),
  }) : _masker = PlateMasker(margin: config.plateMaskMargin);

  final PlateDetector? detector;
  final CarClassifier? classifier;
  final ScanConfig config;
  final PlateMasker _masker;

  bool get isReady => detector != null && classifier != null;

  Future<ScanOutcome> process(img.Image frame) async {
    final detector = this.detector;
    final classifier = this.classifier;
    if (detector == null || classifier == null) {
      return const ScanModelsUnavailable();
    }

    final plates = (await detector.detect(frame))
        .where((p) => p.score >= config.plateScoreThreshold)
        .toList();

    final ratio = plateAreaRatio(plates);
    if (ratio > config.maxPlateAreaRatio) {
      return ScanRejectedPlateTooLarge(ratio);
    }

    final masked = _masker.mask(frame, plates);
    final predictions = await classifier.classify(masked, topK: config.topK);

    if (predictions.isEmpty ||
        predictions.first.confidence < config.minConfidence) {
      return ScanUncertain(predictions);
    }
    return ScanSuccess(maskedFrame: masked, predictions: predictions);
  }

  void close() {
    detector?.close();
    classifier?.close();
  }
}
