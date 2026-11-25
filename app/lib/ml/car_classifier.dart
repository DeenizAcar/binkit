import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:image/image.dart' as img;
import 'package:tflite_flutter/tflite_flutter.dart';

import 'tensor_io.dart';

@immutable
class CarPrediction {
  const CarPrediction(this.label, this.confidence);

  /// Brand name as written in labels.txt. Shown as text, never as a logo.
  final String label;

  /// 0..1
  final double confidence;

  @override
  String toString() => 'CarPrediction($label, $confidence)';
}

abstract interface class CarClassifier {
  /// Classifies a frame whose plates are already masked.
  Future<List<CarPrediction>> classify(img.Image maskedFrame, {int topK = 3});
  void close();
}

/// Parses labels.txt: one label per line, blank lines ignored.
List<String> parseLabels(String text) => [
      for (final line in text.split('\n'))
        if (line.trim().isNotEmpty) line.trim(),
    ];

/// Returns the [k] highest-scoring labels, best first.
List<CarPrediction> topPredictions(
  List<double> scores,
  List<String> labels,
  int k,
) {
  final indices = List<int>.generate(scores.length, (i) => i)
    ..sort((a, b) => scores[b].compareTo(scores[a]));
  return [
    for (final i in indices.take(k))
      CarPrediction(labels[i], scores[i].clamp(0.0, 1.0)),
  ];
}

/// TFLite brand classifier.
///
/// Model contract (see ml/README.md): input [1, h, w, 3] RGB 0..255,
/// output [1, numLabels] probabilities (softmax applied in the model),
/// numLabels == number of lines in labels.txt.
class TfLiteCarClassifier implements CarClassifier {
  TfLiteCarClassifier._(this._interpreter, this._labels);

  static const modelAsset = 'assets/models/car_classifier.tflite';
  static const labelsAsset = 'assets/models/labels.txt';

  final Interpreter _interpreter;
  final List<String> _labels;

  /// Returns null when the model or labels are missing or don't match.
  static Future<TfLiteCarClassifier?> tryLoad() async {
    try {
      final labels = parseLabels(await rootBundle.loadString(labelsAsset));
      final interpreter = await Interpreter.fromAsset(modelAsset);
      final classes = interpreter.getOutputTensor(0).shape.last;
      if (classes != labels.length) {
        interpreter.close();
        debugPrint('Classifier has $classes classes but '
            '${labels.length} labels');
        return null;
      }
      return TfLiteCarClassifier._(interpreter, labels);
    } catch (e) {
      debugPrint('Car classifier unavailable: $e');
      return null;
    }
  }

  @override
  Future<List<CarPrediction>> classify(
    img.Image maskedFrame, {
    int topK = 3,
  }) async {
    final input = _interpreter.getInputTensor(0);
    _interpreter.runInference([imageToInputBytes(maskedFrame, input)]);
    final scores = readOutput(_interpreter.getOutputTensor(0));
    return topPredictions(scores, _labels, topK);
  }

  @override
  void close() => _interpreter.close();
}
