import 'package:image/image.dart' as img;

import 'plate_detector.dart';

/// Paints plate regions solid black, in memory.
///
/// Solid fill instead of blur: a blur can sometimes be partially reversed,
/// a black box cannot.
class PlateMasker {
  const PlateMasker({this.margin = 0.15});

  /// Extra margin around each box, as a fraction of the box size per side.
  final double margin;

  static final _black = img.ColorRgb8(0, 0, 0);

  /// Returns a masked copy of [frame]. The input is not modified.
  img.Image mask(img.Image frame, List<PlateBox> plates) {
    final out = img.Image.from(frame);
    final w = out.width;
    final h = out.height;
    for (final p in plates) {
      final bw = (p.right - p.left) * w;
      final bh = (p.bottom - p.top) * h;
      final x1 = (p.left * w - bw * margin).floor().clamp(0, w - 1);
      final y1 = (p.top * h - bh * margin).floor().clamp(0, h - 1);
      final x2 = (p.right * w + bw * margin).ceil().clamp(0, w - 1);
      final y2 = (p.bottom * h + bh * margin).ceil().clamp(0, h - 1);
      if (x2 < x1 || y2 < y1) continue;
      img.fillRect(out, x1: x1, y1: y1, x2: x2, y2: y2, color: _black);
    }
    return out;
  }
}
