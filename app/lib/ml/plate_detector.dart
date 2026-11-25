import 'package:flutter/foundation.dart';
import 'package:image/image.dart' as img;
import 'package:tflite_flutter/tflite_flutter.dart';

import 'tensor_io.dart';

/// A license plate location in normalized frame coordinates (0..1).
///
/// This is all the detector ever produces: a position. Plate text is never
/// read. The project contains no OCR.
@immutable
class PlateBox {
  const PlateBox({
    required this.left,
    required this.top,
    required this.right,
    required this.bottom,
    required this.score,
  });

  final double left;
  final double top;
  final double right;
  final double bottom;
  final double score;

  /// Box area as a fraction of the frame, clipped to the frame.
  double get area {
    final w = (right.clamp(0.0, 1.0) - left.clamp(0.0, 1.0));
    final h = (bottom.clamp(0.0, 1.0) - top.clamp(0.0, 1.0));
    return (w > 0 && h > 0) ? w * h : 0;
  }

  @override
  String toString() => 'PlateBox($left, $top, $right, $bottom, score: $score)';
}

abstract interface class PlateDetector {
  Future<List<PlateBox>> detect(img.Image frame);
  void close();
}

/// Intersection over union of two boxes.
double plateIou(PlateBox a, PlateBox b) {
  final top = a.top > b.top ? a.top : b.top;
  final left = a.left > b.left ? a.left : b.left;
  final bottom = a.bottom < b.bottom ? a.bottom : b.bottom;
  final right = a.right < b.right ? a.right : b.right;
  final inter = (bottom - top).clamp(0.0, 1.0) * (right - left).clamp(0.0, 1.0);
  final areaA = (a.bottom - a.top) * (a.right - a.left);
  final areaB = (b.bottom - b.top) * (b.right - b.left);
  final union = areaA + areaB - inter;
  return union > 0 ? inter / union : 0;
}

/// Greedy non-maximum suppression. Same algorithm as
/// ml/scripts/convert_plate_detector.py, which measures the shipped model.
List<PlateBox> nonMaxSuppression(
  List<PlateBox> boxes, {
  double scoreThreshold = 0.1,
  double iouThreshold = 0.5,
  int maxBoxes = 20,
}) {
  final candidates = boxes.where((b) => b.score >= scoreThreshold).toList()
    ..sort((a, b) => b.score.compareTo(a.score));
  final kept = <PlateBox>[];
  for (final box in candidates) {
    if (kept.every((k) => plateIou(k, box) <= iouThreshold)) {
      kept.add(box);
      if (kept.length >= maxBoxes) break;
    }
  }
  return kept;
}

/// TFLite plate detector.
///
/// Model contract (see ml/README.md):
/// - input: [1, h, w, 3] RGB, values 0..255 (float32, uint8 or int8)
/// - outputs, either
///   - 2 tensors (any order): boxes [1, N, 4] (ymin, xmin, ymax, xmax,
///     normalized) and scores [1, N], one per anchor, no NMS. The app runs
///     NMS; or
///   - 4 tensors in TF Object Detection API order: boxes, classes, scores,
///     count (NMS already applied).
class TfLitePlateDetector implements PlateDetector {
  TfLitePlateDetector._(this._interpreter);

  static const modelAsset = 'assets/models/plate_detector.tflite';

  /// Boxes below this score are dropped before NMS. Low on purpose: masking
  /// a false positive is harmless. The pipeline applies its own threshold.
  static const preNmsScoreThreshold = 0.1;

  final Interpreter _interpreter;

  /// Returns null when the model asset is missing or invalid.
  static Future<TfLitePlateDetector?> tryLoad() async {
    try {
      final interpreter = await Interpreter.fromAsset(modelAsset);
      final outputs = interpreter.getOutputTensors();
      final ok = switch (outputs.length) {
        2 => outputs.any((t) => t.shape.length == 3 && t.shape.last == 4) &&
            outputs.any((t) => t.shape.length == 2),
        4 => true,
        _ => false,
      };
      if (!ok) {
        interpreter.close();
        debugPrint('Plate detector outputs not supported: '
            '${outputs.map((t) => t.shape).toList()}');
        return null;
      }
      return TfLitePlateDetector._(interpreter);
    } catch (e) {
      debugPrint('Plate detector unavailable: $e');
      return null;
    }
  }

  @override
  Future<List<PlateBox>> detect(img.Image frame) async {
    final input = _interpreter.getInputTensor(0);
    _interpreter.runInference([imageToInputBytes(frame, input)]);

    final outputs = _interpreter.getOutputTensors();
    if (outputs.length == 4) {
      final boxes = readOutput(outputs[0]);
      final scores = readOutput(outputs[2]);
      final count = readOutput(outputs[3]).first.round().clamp(0, scores.length);
      return _toBoxes(boxes, scores, count);
    }

    final boxesTensor =
        outputs.firstWhere((t) => t.shape.length == 3 && t.shape.last == 4);
    final scoresTensor = outputs.firstWhere((t) => t.shape.length == 2);
    final scores = readOutput(scoresTensor);
    final all = _toBoxes(readOutput(boxesTensor), scores, scores.length);
    return nonMaxSuppression(all, scoreThreshold: preNmsScoreThreshold);
  }

  static List<PlateBox> _toBoxes(
      List<double> boxes, List<double> scores, int count) {
    return [
      for (var i = 0; i < count; i++)
        if (i * 4 + 3 < boxes.length)
          PlateBox(
            top: boxes[i * 4],
            left: boxes[i * 4 + 1],
            bottom: boxes[i * 4 + 2],
            right: boxes[i * 4 + 3],
            score: scores[i],
          ),
    ];
  }

  @override
  void close() => _interpreter.close();
}
