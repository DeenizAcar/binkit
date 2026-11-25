import 'dart:typed_data';

import 'package:camera/camera.dart';
import 'package:image/image.dart' as img;

/// A copy of one YUV420 camera frame, held only in memory.
///
/// Plain data so it can be sent to a background isolate. Never written to
/// disk.
class YuvFrame {
  const YuvFrame({
    required this.width,
    required this.height,
    required this.y,
    required this.u,
    required this.v,
    required this.yRowStride,
    required this.uvRowStride,
    required this.uvPixelStride,
    required this.rotationDegrees,
  });

  /// Copies the plane bytes out of [image]; the camera reuses its buffers.
  factory YuvFrame.fromCameraImage(CameraImage image, int rotationDegrees) {
    if (image.planes.length != 3) {
      throw StateError(
          'Expected 3 YUV planes, got ${image.planes.length} (${image.format.group})');
    }
    final p = image.planes;
    return YuvFrame(
      width: image.width,
      height: image.height,
      y: Uint8List.fromList(p[0].bytes),
      u: Uint8List.fromList(p[1].bytes),
      v: Uint8List.fromList(p[2].bytes),
      yRowStride: p[0].bytesPerRow,
      uvRowStride: p[1].bytesPerRow,
      uvPixelStride: p[1].bytesPerPixel ?? 1,
      rotationDegrees: rotationDegrees,
    );
  }

  final int width;
  final int height;
  final Uint8List y;
  final Uint8List u;
  final Uint8List v;
  final int yRowStride;
  final int uvRowStride;
  final int uvPixelStride;
  final int rotationDegrees;
}

/// Converts a YUV420 frame to an upright RGB image (BT.601).
img.Image yuvFrameToImage(YuvFrame f) {
  final rgb = Uint8List(f.width * f.height * 3);
  var o = 0;
  for (var row = 0; row < f.height; row++) {
    final yBase = row * f.yRowStride;
    final uvBase = (row >> 1) * f.uvRowStride;
    for (var col = 0; col < f.width; col++) {
      final yi = yBase + col;
      final uvi = uvBase + (col >> 1) * f.uvPixelStride;
      final yy = yi < f.y.length ? f.y[yi] : 0;
      final uu = (uvi < f.u.length ? f.u[uvi] : 128) - 128;
      final vv = (uvi < f.v.length ? f.v[uvi] : 128) - 128;
      rgb[o++] = _clamp(yy + 1.402 * vv);
      rgb[o++] = _clamp(yy - 0.344136 * uu - 0.714136 * vv);
      rgb[o++] = _clamp(yy + 1.772 * uu);
    }
  }
  final image = img.Image.fromBytes(
    width: f.width,
    height: f.height,
    bytes: rgb.buffer,
    numChannels: 3,
  );
  return f.rotationDegrees % 360 == 0
      ? image
      : img.copyRotate(image, angle: f.rotationDegrees);
}

int _clamp(double v) => v < 0 ? 0 : (v > 255 ? 255 : v.round());
