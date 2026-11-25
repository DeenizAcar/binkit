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

/// TFLite plate detector.
///
/// Model contract (see ml/README.md):
/// - input: [1, h, w, 3] RGB, values 0..255 (float32, uint8 or int8)
/// - outputs, either
///   - 2 tensors: boxes [1, N, 4] (ymin, xmin, ymax, xmax, normalized),
///     scores [1, N]; or
///   - 4 tensors in TF Object Detection API order: boxes, classes, scores,
///     count.
class TfLitePlateDetector implements PlateDetector {
  TfLitePlateDetector._(this._interpreter);

  static const modelAsset = 'assets/models/plate_detector.tflite';

  final Interpreter _interpreter;

  /// Returns null when the model asset is missing or invalid.
  static Future<TfLitePlateDetector?> tryLoad() async {
    try {
      final interpreter = await Interpreter.fromAsset(modelAsset);
      final outputs = interpreter.getOutputTensors().length;
      if (outputs != 2 && outputs != 4) {
        interpreter.close();
        debugPrint('Plate detector has $outputs outputs, expected 2 or 4');
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
    final boxes = readOutput(outputs[0]);
    final scores = readOutput(outputs.length == 4 ? outputs[2] : outputs[1]);
    var count = scores.length;
    if (outputs.length == 4) {
      count = readOutput(outputs[3]).first.round().clamp(0, scores.length);
    }

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
