"""Download Open Images V7 'Vehicle registration plate' boxes and images.

Location boxes only. No plate text is read or stored anywhere.

Annotations: CC BY 4.0 (Google). Images: listed as CC BY 2.0 (Flickr authors).
Sources are Google's and AWS's official public buckets.

Usage (from the repo root):
  python -I ml/scripts/fetch_openimages_plates.py [--max-train 8000] [--workers 8]

Output (git-ignored):
  ml/data/openimages_plates/{train,validation,test}/images/<id>.jpg   (longest side <= 640)
  ml/data/openimages_plates/{split}/boxes.csv   image_id,xmin,ymin,xmax,ymax (normalized)
"""

from __future__ import annotations

import argparse
import csv
import io
import sys
import urllib.request
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

PLATE = "/m/01jfm_"  # Vehicle registration plate
ANNOTATIONS = {
    "train": "https://storage.googleapis.com/openimages/v6/oidv6-train-annotations-bbox.csv",
    "validation": "https://storage.googleapis.com/openimages/v5/validation-annotations-bbox.csv",
    "test": "https://storage.googleapis.com/openimages/v5/test-annotations-bbox.csv",
}
IMAGE_URL = "https://s3.amazonaws.com/open-images-dataset/{split}/{image_id}.jpg"
REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "ml" / "data" / "openimages_plates"
UA = {"User-Agent": "open-images-subset-downloader/0.1 (python-urllib)"}
MAX_SIDE = 640


def stream_boxes(split: str) -> dict[str, list[tuple[float, float, float, float]]]:
    """Streams the annotation CSV and keeps plate boxes only."""
    boxes: dict[str, list] = defaultdict(list)
    req = urllib.request.Request(ANNOTATIONS[split], headers=UA)
    with urllib.request.urlopen(req, timeout=120) as r:
        reader = csv.DictReader(io.TextIOWrapper(r, encoding="utf-8"))
        for i, row in enumerate(reader):
            if row["LabelName"] == PLATE:
                boxes[row["ImageID"]].append(tuple(
                    float(row[k]) for k in ("XMin", "YMin", "XMax", "YMax")))
            if i and i % 2_000_000 == 0:
                print(f"  {split}: {i:,} rows scanned, {len(boxes):,} images with plates", flush=True)
    return boxes


def fetch_image(split: str, image_id: str, target: Path) -> bool:
    from PIL import Image  # imported here so --help works without Pillow

    if target.exists():
        return True
    req = urllib.request.Request(IMAGE_URL.format(split=split, image_id=image_id), headers=UA)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            data = r.read()
        img = Image.open(io.BytesIO(data)).convert("RGB")
        img.thumbnail((MAX_SIDE, MAX_SIDE))
        img.save(target, "JPEG", quality=90)
        return True
    except Exception as e:  # noqa: BLE001 - log and skip broken images
        print(f"  skip {image_id}: {e}", file=sys.stderr)
        return False


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--max-train", type=int, default=8000)
    p.add_argument("--workers", type=int, default=8)
    p.add_argument("--splits", nargs="*", default=["validation", "test", "train"])
    args = p.parse_args()

    for split in args.splits:
        print(f"{split}: reading annotations...", flush=True)
        boxes = stream_boxes(split)
        ids = sorted(boxes)
        if split == "train":
            ids = ids[: args.max_train]
        img_dir = OUT / split / "images"
        img_dir.mkdir(parents=True, exist_ok=True)

        ok: set[str] = set()
        with ThreadPoolExecutor(args.workers) as pool:
            futures = {pool.submit(fetch_image, split, i, img_dir / f"{i}.jpg"): i for i in ids}
            for n, f in enumerate(as_completed(futures), 1):
                if f.result():
                    ok.add(futures[f])
                if n % 500 == 0:
                    print(f"  {split}: {n}/{len(ids)} images", flush=True)

        with (OUT / split / "boxes.csv").open("w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["image_id", "xmin", "ymin", "xmax", "ymax"])
            for i in sorted(ok):
                for b in boxes[i]:
                    w.writerow([i, *b])
        n_boxes = sum(len(boxes[i]) for i in ok)
        print(f"{split}: {len(ok)} images, {n_boxes} plate boxes", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
