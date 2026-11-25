import 'dart:typed_data';

import 'package:bink_it/ml/car_classifier.dart';
import 'package:bink_it/ml/plate_detector.dart';
import 'package:bink_it/ml/plate_masker.dart';
import 'package:bink_it/ml/tensor_io.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:image/image.dart' as img;
import 'package:tflite_flutter/tflite_flutter.dart';

void main() {
  group('PlateMasker', () {
    test('paints the box and margin black, leaves the rest', () {
      final frame = img.Image(width: 100, height: 100)
        ..clear(img.ColorRgb8(200, 200, 200));
      const plate =
          PlateBox(left: 0.4, top: 0.4, right: 0.6, bottom: 0.5, score: 1);

      final out = const PlateMasker(margin: 0.1).mask(frame, [plate]);

      expect(out.getPixel(50, 45).r, 0);
      expect(out.getPixel(38, 45).r, 0, reason: 'inside 10% margin');
      expect(out.getPixel(30, 45).r, 200);
      expect(frame.getPixel(50, 45).r, 200, reason: 'input not mutated');
    });

    test('clips boxes outside the frame', () {
      final frame = img.Image(width: 10, height: 10);
      const plate =
          PlateBox(left: 0.8, top: 0.8, right: 1.5, bottom: 1.5, score: 1);
      expect(() => const PlateMasker().mask(frame, [plate]), returnsNormally);
    });
  });

  test('parseLabels skips blank lines and trims', () {
    expect(parseLabels('Toyota\r\n\n Honda \nBMW\n'), ['Toyota', 'Honda', 'BMW']);
  });

  test('topPredictions sorts best first', () {
    final top = topPredictions([0.1, 0.7, 0.2], ['A', 'B', 'C'], 2);
    expect(top.map((p) => p.label), ['B', 'C']);
  });

  group('tensor encoding', () {
    test('float32 input keeps 0..255 values', () {
      final bytes =
          encodeInput(Uint8List.fromList([0, 128, 255]), TensorType.float32, 0, 0);
      expect(bytes.buffer.asFloat32List(), [0, 128, 255]);
    });

    test('int8 input applies quantization', () {
      final bytes =
          encodeInput(Uint8List.fromList([0, 255]), TensorType.int8, 1, -128);
      expect(bytes.buffer.asInt8List(), [-128, 127]);
    });

    test('uint8 output is dequantized', () {
      final values =
          decodeOutput(Uint8List.fromList([0, 255]), TensorType.uint8, 1 / 255, 0);
      expect(values[0], 0);
      expect(values[1], closeTo(1, 1e-9));
    });
  });
}
