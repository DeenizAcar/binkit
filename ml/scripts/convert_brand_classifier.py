"""Convert the brand classifier ONNX to TFLite, verify it, measure it, install it.

Run in the conversion venv:
  ml/.venv-convert/Scripts/python.exe -I ml/scripts/convert_brand_classifier.py [--install]

Checks TFLite vs the PyTorch reference, then measures the float16 model on the
test split (top-1, top-3, answered rate and accuracy at the app's 0.6
threshold). --install copies the model and labels.txt into the app.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
from tflite_utils import load_interpreter, onnx_to_tflite  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
RUNS = REPO / "ml" / "runs" / "brand"
DATA = REPO / "ml" / "data" / "brands"
APP_MODELS = REPO / "app" / "assets" / "models"


def run(interp, image_nhwc: np.ndarray) -> np.ndarray:
    inp = interp.get_input_details()[0]
    interp.set_tensor(inp["index"], image_nhwc.astype(inp["dtype"]))
    interp.invoke()
    return interp.get_tensor(interp.get_output_details()[0]["index"])[0]


def main() -> int:
    global DATA, RUNS
    p = argparse.ArgumentParser()
    p.add_argument("--min-confidence", type=float, default=0.6)
    p.add_argument("--install", action="store_true")
    p.add_argument("--data", type=Path, default=DATA)
    p.add_argument("--runs", type=Path, default=RUNS)
    args = p.parse_args()
    DATA, RUNS = args.data, args.runs

    labels = (RUNS / "labels.txt").read_text(encoding="utf-8").splitlines()
    onnx = RUNS / "brand_classifier.onnx"
    samples = sorted((DATA / "val").rglob("*.jpg"))
    f32, f16 = onnx_to_tflite(onnx, RUNS, samples)

    ref = np.load(onnx.with_suffix(".reference.npz"))
    image_nhwc = np.transpose(ref["image"], (0, 2, 3, 1))
    for path in (f32, f16):
        diff = np.abs(run(load_interpreter(path), image_nhwc) - ref["probs"][0]).max()
        print(f"{path.name}: max |prob diff| {diff:.5f}, {path.stat().st_size / 1e6:.1f} MB")
        if diff > 0.01:
            print("  MISMATCH vs PyTorch reference", file=sys.stderr)
            return 1

    interp = load_interpreter(f16)
    h, w = interp.get_input_details()[0]["shape"][1:3]
    top1 = top3 = answered = correct_answered = n = 0
    for k, label in enumerate(labels):
        for img_path in sorted((DATA / "test" / label).glob("*.jpg")):
            x = np.asarray(Image.open(img_path).convert("RGB").resize((int(w), int(h)), Image.BILINEAR),
                           np.float32)[None]
            probs = run(interp, x)
            order = np.argsort(-probs)
            n += 1
            top1 += order[0] == k
            top3 += k in order[:3]
            if probs[order[0]] >= args.min_confidence:
                answered += 1
                correct_answered += order[0] == k
    metrics = {
        "model": f16.name, "test_images": n,
        "top1": top1 / n, "top3": top3 / n,
        "answered_rate": answered / n,
        "accuracy_when_answered": correct_answered / max(answered, 1),
        "min_confidence": args.min_confidence,
    }
    print("TFLite float16 test:", json.dumps(metrics))
    (RUNS / "tflite_metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")

    if args.install:
        APP_MODELS.mkdir(parents=True, exist_ok=True)
        shutil.copy(f16, APP_MODELS / "car_classifier.tflite")
        shutil.copy(RUNS / "labels.txt", APP_MODELS / "labels.txt")
        print("installed car_classifier.tflite + labels.txt")
    return 0


if __name__ == "__main__":
    sys.exit(main())
