import 'dart:typed_data';

import 'package:bink_it/features/scanner/frame_converter.dart';
import 'package:flutter_test/flutter_test.dart';

YuvFrame frame({
  required int y,
  required int u,
  required int v,
  int rotation = 0,
}) {
  const w = 4, h = 2;
  return YuvFrame(
    width: w,
    height: h,
    y: Uint8List(w * h)..fillRange(0, w * h, y),
    u: Uint8List(2)..fillRange(0, 2, u),
    v: Uint8List(2)..fillRange(0, 2, v),
    yRowStride: w,
    uvRowStride: 2,
    uvPixelStride: 1,
    rotationDegrees: rotation,
  );
}

void main() {
  test('neutral chroma gives gray', () {
    final image = yuvFrameToImage(frame(y: 128, u: 128, v: 128));
    final p = image.getPixel(1, 1);
    expect([p.r, p.g, p.b], [128, 128, 128]);
  });

  test('high V gives red', () {
    final p = yuvFrameToImage(frame(y: 76, u: 85, v: 255)).getPixel(0, 0);
    expect(p.r, greaterThan(240));
    expect(p.g, lessThan(20));
    expect(p.b, lessThan(20));
  });

  test('rotation swaps dimensions', () {
    final image = yuvFrameToImage(frame(y: 0, u: 128, v: 128, rotation: 90));
    expect([image.width, image.height], [2, 4]);
  });
}
