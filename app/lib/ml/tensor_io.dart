import 'dart:math' as math;
import 'dart:typed_data';

import 'package:image/image.dart' as img;
import 'package:tflite_flutter/tflite_flutter.dart';

/// Resizes [image] to the model's input size and returns the raw tensor
/// bytes for an NHWC RGB input.
///
/// Contract with the training side (see ml/README.md): the full frame is
/// resized (not cropped) to the input size, and pixel values are fed as
/// 0..255. Any normalization lives inside the model.
Uint8List imageToInputBytes(img.Image image, Tensor input) {
  final shape = input.shape; // [1, height, width, 3]
  if (shape.length != 4 || shape[3] != 3) {
    throw StateError('Unsupported input shape $shape, expected [1,h,w,3]');
  }
  final resized = img.copyResize(
    image,
    width: shape[2],
    height: shape[1],
    interpolation: img.Interpolation.linear,
  );
  final rgb = resized.getBytes(order: img.ChannelOrder.rgb);
  return encodeInput(rgb, input.type, input.params.scale, input.params.zeroPoint);
}

/// Converts 0..255 pixel values to tensor bytes of the given [type],
/// applying quantization when the tensor is quantized.
Uint8List encodeInput(
  Uint8List rgb,
  TensorType type,
  double scale,
  int zeroPoint,
) {
  switch (type) {
    case TensorType.float32:
      final out = Float32List(rgb.length);
      for (var i = 0; i < rgb.length; i++) {
        out[i] = rgb[i].toDouble();
      }
      return out.buffer.asUint8List();
    case TensorType.uint8:
      if (scale == 0 || (scale == 1 && zeroPoint == 0)) return rgb;
      final out = Uint8List(rgb.length);
      for (var i = 0; i < rgb.length; i++) {
        out[i] = _quantize(rgb[i], scale, zeroPoint, 0, 255);
      }
      return out;
    case TensorType.int8:
      final out = Int8List(rgb.length);
      final s = scale == 0 ? 1.0 : scale;
      for (var i = 0; i < rgb.length; i++) {
        out[i] = _quantize(rgb[i], s, zeroPoint, -128, 127);
      }
      return out.buffer.asUint8List();
    default:
      throw StateError('Unsupported input tensor type $type');
  }
}

int _quantize(int value, double scale, int zeroPoint, int lo, int hi) {
  final q = (value / scale).round() + zeroPoint;
  return math.max(lo, math.min(hi, q));
}

/// Reads a tensor's values as doubles, dequantizing if needed.
List<double> readOutput(Tensor tensor) =>
    decodeOutput(tensor.data, tensor.type, tensor.params.scale, tensor.params.zeroPoint);

List<double> decodeOutput(
  Uint8List bytes,
  TensorType type,
  double scale,
  int zeroPoint,
) {
  // Copy so the result does not alias native tensor memory.
  final data = Uint8List.fromList(bytes);
  switch (type) {
    case TensorType.float32:
      return data.buffer.asFloat32List().toList();
    case TensorType.uint8:
      final s = scale == 0 ? 1.0 : scale;
      return [for (final v in data) (v - zeroPoint) * s];
    case TensorType.int8:
      final s = scale == 0 ? 1.0 : scale;
      return [for (final v in data.buffer.asInt8List()) (v - zeroPoint) * s];
    default:
      throw StateError('Unsupported output tensor type $type');
  }
}
