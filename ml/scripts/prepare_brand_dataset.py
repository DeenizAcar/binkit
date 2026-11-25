"""Clean, crop and plate-mask the Commons brand images for classifier training.

For every image in ml/data/commons/manifest.csv:
  1. find the largest car with a COCO-pretrained detector (torchvision
     Faster R-CNN MobileNetV3, BSD-3-Clause); drop the image if there is no
     clear car (this removes logos, interiors, toys, documents, ...)
  2. crop that car with some padding (matches how users frame a car)
  3. run OUR plate detector on the crop and paint plates black, exactly like
     the app (score >= 0.4 after NMS, 15% margin), so the classifier trains on
     the same kind of images it sees in the app
  4. assign a deterministic train/val/test split by page id

Plates are only located and painted over. Nothing reads plate text.

Usage (CUDA venv, after the plate detector is trained):
  ml/.venv-torch/Scripts/python.exe -I ml/scripts/prepare_brand_dataset.py
Output: ml/data/brands/{train,val,test}/<brand>/<pageid>.jpg + report.csv (git-ignored)
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import sys
from collections import Counter
from pathlib import Path

import torch
from PIL import Image, ImageDraw
from torchvision.models.detection import (
    FasterRCNN_MobileNet_V3_Large_FPN_Weights,
    fasterrcnn_mobilenet_v3_large_fpn,
)
from torchvision.transforms.functional import pil_to_tensor

sys.path.insert(0, str(Path(__file__).resolve().parent))
from export_plate_detector import ExportablePlateDetector  # noqa: E402
from train_plate_detector import INPUT_SIZE, RUNS, build_model  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
COMMONS = REPO / "ml" / "data" / "commons"
OUT = REPO / "ml" / "data" / "brands"
COCO_CAR = 3  # COCO category id for "car"

# Same values as app/lib/config/scan_config.dart and plate_detector.dart.
PLATE_SCORE = 0.4
PLATE_MARGIN = 0.15
MAX_PLATE_AREA = 0.15  # the app rejects such frames; skip them here too
PRE_NMS_SCORE = 0.1
NMS_IOU = 0.5


def split_of(pageid: str) -> str:
    h = int(hashlib.sha1(pageid.encode()).hexdigest(), 16) % 100
    return "train" if h < 70 else ("val" if h < 85 else "test")


def nms(boxes: torch.Tensor, scores: torch.Tensor) -> list[int]:
    """Greedy NMS identical to the app (boxes: ymin, xmin, ymax, xmax)."""
    order = [int(i) for i in torch.argsort(scores, descending=True) if scores[i] >= PRE_NMS_SCORE]
    kept: list[int] = []
    for i in order:
        ok = True
        for j in kept:
            a, b = boxes[i], boxes[j]
            ih = max(0.0, float(min(a[2], b[2]) - max(a[0], b[0])))
            iw = max(0.0, float(min(a[3], b[3]) - max(a[1], b[1])))
            inter = ih * iw
            union = float((a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1])) - inter
            if union > 0 and inter / union > NMS_IOU:
                ok = False
                break
        if ok:
            kept.append(i)
            if len(kept) >= 20:
                break
    return kept


def mask_plates(img: Image.Image, plate_model, device) -> tuple[Image.Image, int, float]:
    x = pil_to_tensor(img.resize((INPUT_SIZE, INPUT_SIZE), Image.BILINEAR)).float()[None].to(device)
    with torch.no_grad():
        boxes, scores = plate_model(x)
    boxes, scores = boxes[0].cpu(), scores[0].cpu()
    w, h = img.size
    out = img.copy()
    draw = ImageDraw.Draw(out)
    n = 0
    area = 0.0
    for i in nms(boxes, scores):
        if scores[i] < PLATE_SCORE:
            continue
        top, left, bottom, right = boxes[i].tolist()
        area += max(0.0, bottom - top) * max(0.0, right - left)
        bw, bh = (right - left) * w, (bottom - top) * h
        draw.rectangle([left * w - bw * PLATE_MARGIN, top * h - bh * PLATE_MARGIN,
                        right * w + bw * PLATE_MARGIN, bottom * h + bh * PLATE_MARGIN], fill=(0, 0, 0))
        n += 1
    return out, n, min(1.0, area)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--plate-weights", type=Path, default=RUNS / "best.pt")
    p.add_argument("--min-car-area", type=float, default=0.12,
                   help="largest car must cover this fraction of the photo")
    p.add_argument("--min-car-score", type=float, default=0.7)
    p.add_argument("--pad", type=float, default=0.08)
    p.add_argument("--out", type=Path, default=OUT)
    p.add_argument("--only", nargs="*", help="brand labels to process (smoke tests)")
    args = p.parse_args()

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    car_model = fasterrcnn_mobilenet_v3_large_fpn(
        weights=FasterRCNN_MobileNet_V3_Large_FPN_Weights.COCO_V1).eval().to(device)
    plate = build_model(pretrained=False)
    plate.load_state_dict(torch.load(args.plate_weights, map_location="cpu"))
    plate_model = ExportablePlateDetector(plate).eval().to(device)

    with (COMMONS / "manifest.csv").open(encoding="utf-8") as f:
        rows = [r for r in csv.DictReader(f) if (COMMONS / r["file"]).exists()
                and (not args.only or r["brand"] in args.only)]

    report = []
    counts: Counter = Counter()
    for k, r in enumerate(rows, 1):
        try:
            img = Image.open(COMMONS / r["file"]).convert("RGB")
        except OSError:
            report.append({**r, "status": "unreadable"})
            continue
        with torch.no_grad():
            det = car_model([pil_to_tensor(img).float().div(255).to(device)])[0]
        w, h = img.size
        cars = [(b.tolist(), float(s)) for b, s, l in zip(det["boxes"], det["scores"], det["labels"])
                if int(l) == COCO_CAR and float(s) >= args.min_car_score]
        if not cars:
            report.append({**r, "status": "no_car"})
            continue
        (x1, y1, x2, y2), _ = max(cars, key=lambda c: (c[0][2] - c[0][0]) * (c[0][3] - c[0][1]))
        if (x2 - x1) * (y2 - y1) / (w * h) < args.min_car_area:
            report.append({**r, "status": "car_too_small"})
            continue
        px, py = (x2 - x1) * args.pad, (y2 - y1) * args.pad
        crop = img.crop((max(0, x1 - px), max(0, y1 - py), min(w, x2 + px), min(h, y2 + py)))
        masked, n_plates, plate_area = mask_plates(crop, plate_model, device)
        if plate_area > MAX_PLATE_AREA:
            report.append({**r, "status": "plate_too_large"})
            continue

        split = split_of(r["pageid"])
        target = args.out / split / r["brand"] / f"{r['pageid']}.jpg"
        target.parent.mkdir(parents=True, exist_ok=True)
        masked.save(target, "JPEG", quality=92)
        counts[(r["brand"], split)] += 1
        report.append({**r, "status": f"ok:{split}:plates={n_plates}"})
        if k % 500 == 0:
            print(f"{k}/{len(rows)} processed", flush=True)

    args.out.mkdir(parents=True, exist_ok=True)
    with (args.out / "report.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=[*rows[0].keys(), "status"])
        w.writeheader()
        w.writerows(report)

    brands = sorted({b for b, _ in counts})
    print(f"{'brand':15} train   val  test")
    for b in brands:
        print(f"{b:15} {counts[(b, 'train')]:5} {counts[(b, 'val')]:5} {counts[(b, 'test')]:5}")
    status = Counter(s["status"].split(":")[0] for s in report)
    print(dict(status))
    return 0


if __name__ == "__main__":
    sys.exit(main())
