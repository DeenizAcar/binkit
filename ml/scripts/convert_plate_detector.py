"""Convert the exported ONNX plate detector to TFLite and verify it.

Run in the conversion venv (onnx2tf + TensorFlow, CPU):
  ml/.venv-convert/Scripts/python.exe -I ml/scripts/convert_plate_detector.py

Steps:
  1. onnx2tf: ONNX (NCHW) -> TFLite float32 + float16, input NHWC [1, 320, 320, 3]
  2. compare TFLite outputs with the PyTorch reference (max abs difference)
  3. evaluate AP50 / recall on a split with the same NMS the app uses
  4. copy the float16 model to app/assets/models/plate_detector.tflite (--install)
"""

from __future__ import annotations

import argparse
import csv
import shutil
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
from tflite_utils import load_interpreter, onnx_to_tflite  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
RUNS = REPO / "ml" / "runs" / "plate"
DATA = REPO / "ml" / "data" / "openimages_plates"
APP_MODEL = REPO / "app" / "assets" / "models" / "plate_detector.tflite"


def run(interp, image_nhwc: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    inp = interp.get_input_details()[0]
    interp.set_tensor(inp["index"], image_nhwc.astype(inp["dtype"]))
    interp.invoke()
    outs = interp.get_output_details()
    tensors = [interp.get_tensor(o["index"]) for o in outs]
    boxes = next(t for t in tensors if t.ndim == 3 and t.shape[-1] == 4)
    scores = next(t for t in tensors if t.ndim == 2)
    return boxes[0], scores[0]


def nms(boxes: np.ndarray, scores: np.ndarray, score_thr: float = 0.1,
        iou_thr: float = 0.5, max_boxes: int = 20):
    """Greedy NMS, identical to nonMaxSuppression() in app/lib/ml/plate_detector.dart."""
    keep_idx = np.where(scores >= score_thr)[0]
    order = keep_idx[np.argsort(-scores[keep_idx], kind="stable")]
    kept = []
    for i in order:
        if all(iou(boxes[i], boxes[j]) <= iou_thr for j in kept):
            kept.append(i)
            if len(kept) >= max_boxes:
                break
    return kept


def iou(a, b) -> float:
    y1, x1 = max(a[0], b[0]), max(a[1], b[1])
    y2, x2 = min(a[2], b[2]), min(a[3], b[3])
    inter = max(0.0, y2 - y1) * max(0.0, x2 - x1)
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


def evaluate(interp, split: str, limit: int | None) -> dict:
    gt: dict[str, list] = defaultdict(list)
    with (DATA / split / "boxes.csv").open(encoding="utf-8") as f:
        for r in csv.DictReader(f):
            # stored as xmin, ymin, xmax, ymax -> app order ymin, xmin, ymax, xmax
            gt[r["image_id"]].append([float(r["ymin"]), float(r["xmin"]), float(r["ymax"]), float(r["xmax"])])
    ids = sorted(gt)[:limit] if limit else sorted(gt)
    size = interp.get_input_details()[0]["shape"][1:3]
    scored, n_gt, recalled = [], 0, 0
    for image_id in ids:
        img = Image.open(DATA / split / "images" / f"{image_id}.jpg").convert("RGB")
        x = np.asarray(img.resize((int(size[1]), int(size[0])), Image.BILINEAR), dtype=np.float32)[None]
        boxes, scores = run(interp, x)
        kept = nms(boxes, scores)
        g = gt[image_id]
        n_gt += len(g)
        matched = [False] * len(g)
        for i in kept:
            ious = [iou(boxes[i], gb) for gb in g]
            j = int(np.argmax(ious)) if ious else -1
            tp = j >= 0 and ious[j] >= 0.5 and not matched[j]
            if tp:
                matched[j] = True
                recalled += scores[i] >= 0.4
            scored.append((float(scores[i]), tp))
    scored.sort(key=lambda s: -s[0])
    tp = np.cumsum([s[1] for s in scored])
    fp = np.cumsum([not s[1] for s in scored])
    prec = tp / np.maximum(tp + fp, 1)
    rec = tp / max(n_gt, 1)
    ap, prev = 0.0, 0.0
    for k in range(len(prec)):
        ap += (rec[k] - prev) * prec[k:].max()
        prev = rec[k]
    return {"images": len(ids), "boxes": n_gt, "ap50": ap, "recall@0.4": recalled / max(n_gt, 1)}


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--onnx", type=Path, default=RUNS / "plate_detector.onnx")
    p.add_argument("--split", default="test")
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--install", action="store_true", help="copy float16 model into the app")
    args = p.parse_args()

    samples = sorted((DATA / "validation" / "images").glob("*.jpg"))
    f32, f16 = onnx_to_tflite(args.onnx, RUNS, samples)
    ref = np.load(args.onnx.with_suffix(".reference.npz"))
    image_nhwc = np.transpose(ref["image"], (0, 2, 3, 1))
    for path in (f32, f16):
        boxes, scores = run(load_interpreter(path), image_nhwc)
        db = np.abs(boxes - ref["boxes"][0]).max()
        ds = np.abs(scores - ref["scores"][0]).max()
        print(f"{path.name}: input {load_interpreter(path).get_input_details()[0]['shape']}, "
              f"max |boxes diff| {db:.5f}, max |scores diff| {ds:.5f}, {path.stat().st_size / 1e6:.1f} MB")
        if db > 0.01 or ds > 0.01:
            print("  MISMATCH vs PyTorch reference", file=sys.stderr)
            return 1

    metrics = evaluate(load_interpreter(f16), args.split, args.limit)
    print(f"TFLite float16 on {args.split}: {metrics}")

    if args.install:
        APP_MODEL.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(f16, APP_MODEL)
        print(f"installed {APP_MODEL.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
