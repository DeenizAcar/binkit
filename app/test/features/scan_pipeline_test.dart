import 'package:bink_it/config/scan_config.dart';
import 'package:bink_it/features/scanner/scan_pipeline.dart';
import 'package:bink_it/ml/car_classifier.dart';
import 'package:bink_it/ml/plate_detector.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:image/image.dart' as img;

class FakeDetector implements PlateDetector {
  FakeDetector(this.boxes);
  final List<PlateBox> boxes;
  int calls = 0;

  @override
  Future<List<PlateBox>> detect(img.Image frame) async {
    calls++;
    return boxes;
  }

  @override
  void close() {}
}

class FakeClassifier implements CarClassifier {
  FakeClassifier(this.predictions);
  final List<CarPrediction> predictions;
  img.Image? lastInput;

  @override
  Future<List<CarPrediction>> classify(img.Image maskedFrame,
      {int topK = 3}) async {
    lastInput = maskedFrame;
    return predictions.take(topK).toList();
  }

  @override
  void close() {}
}

PlateBox box(double l, double t, double r, double b, [double score = 0.9]) =>
    PlateBox(left: l, top: t, right: r, bottom: b, score: score);

img.Image whiteFrame() =>
    img.Image(width: 100, height: 100)..clear(img.ColorRgb8(255, 255, 255));

const confident = [
  CarPrediction('Toyota', 0.91),
  CarPrediction('Honda', 0.05),
  CarPrediction('Mazda', 0.02),
  CarPrediction('Ford', 0.01),
];

void main() {
  test('fails closed without a plate detector', () async {
    final classifier = FakeClassifier(confident);
    final pipeline = ScanPipeline(detector: null, classifier: classifier);

    expect(await pipeline.process(whiteFrame()), isA<ScanModelsUnavailable>());
    expect(classifier.lastInput, isNull);
  });

  test('rejects when plates cover more than 15% of the frame', () async {
    final classifier = FakeClassifier(confident);
    final pipeline = ScanPipeline(
      detector: FakeDetector([box(0.1, 0.1, 0.5, 0.5)]), // 16%
      classifier: classifier,
    );

    final outcome = await pipeline.process(whiteFrame());

    expect(outcome, isA<ScanRejectedPlateTooLarge>());
    expect((outcome as ScanRejectedPlateTooLarge).plateAreaRatio,
        closeTo(0.16, 1e-9));
    expect(classifier.lastInput, isNull, reason: 'must not classify');
  });

  test('accepts plates covering exactly the threshold', () async {
    final pipeline = ScanPipeline(
      detector: FakeDetector([box(0, 0, 0.5, 0.3)]), // 15%
      classifier: FakeClassifier(confident),
    );
    expect(await pipeline.process(whiteFrame()), isA<ScanSuccess>());
  });

  test('ignores low-score boxes for rejection and masking', () async {
    final classifier = FakeClassifier(confident);
    final pipeline = ScanPipeline(
      detector: FakeDetector([box(0, 0, 1, 1, 0.1)]),
      classifier: classifier,
    );

    expect(await pipeline.process(whiteFrame()), isA<ScanSuccess>());
    final p = classifier.lastInput!.getPixel(50, 50);
    expect(p.r, 255);
  });

  test('classifier only ever sees the masked frame', () async {
    final frame = whiteFrame();
    final classifier = FakeClassifier(confident);
    final pipeline = ScanPipeline(
      detector: FakeDetector([box(0.4, 0.8, 0.6, 0.9)]),
      classifier: classifier,
    );

    final outcome = await pipeline.process(frame) as ScanSuccess;

    final seen = classifier.lastInput!;
    expect(seen.getPixel(50, 85).r, 0, reason: 'plate area masked');
    expect(seen.getPixel(5, 5).r, 255, reason: 'rest untouched');
    expect(identical(outcome.maskedFrame, seen), isTrue);
    expect(frame.getPixel(50, 85).r, 255, reason: 'input not mutated');
  });

  test('returns uncertain below the confidence threshold', () async {
    final pipeline = ScanPipeline(
      detector: FakeDetector(const []),
      classifier: FakeClassifier(const [
        CarPrediction('Toyota', 0.41),
        CarPrediction('Honda', 0.38),
      ]),
    );

    final outcome = await pipeline.process(whiteFrame());
    expect(outcome, isA<ScanUncertain>());
  });

  test('returns top-k predictions on success', () async {
    final pipeline = ScanPipeline(
      detector: FakeDetector(const []),
      classifier: FakeClassifier(confident),
      config: const ScanConfig(topK: 3),
    );

    final outcome = await pipeline.process(whiteFrame()) as ScanSuccess;
    expect(outcome.predictions.map((p) => p.label),
        ['Toyota', 'Honda', 'Mazda']);
    expect(outcome.top.label, 'Toyota');
  });

  test('plateAreaRatio clips boxes and caps at 1', () {
    expect(plateAreaRatio([box(-0.5, -0.5, 0.5, 0.5)]), closeTo(0.25, 1e-9));
    expect(plateAreaRatio([box(0, 0, 1, 1), box(0, 0, 1, 1)]), 1);
    expect(plateAreaRatio(const []), 0);
  });
}
