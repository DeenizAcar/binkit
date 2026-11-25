"""Train the car brand classifier (torchvision MobileNetV3-Large, ImageNet init).

Trains on plate-masked crops from prepare_brand_dataset.py. Reports the test
set the way the app behaves: top-1/top-3 accuracy, plus how often the model is
confident enough to answer (>= --min-confidence, app default 0.6) and how
accurate it is when it does.

Usage (CUDA venv):
  ml/.venv-torch/Scripts/python.exe -I ml/scripts/train_brand_classifier.py --epochs 30
  ml/.venv-torch/Scripts/python.exe -I ml/scripts/train_brand_classifier.py --export
Output: ml/runs/brand/{best.pt, labels.txt, metrics.json, brand_classifier.onnx}
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from collections import Counter
from pathlib import Path

import numpy as np
import torch
from torch import nn
from torch.utils.data import DataLoader, WeightedRandomSampler
from torchvision import datasets
from torchvision.models import MobileNet_V3_Large_Weights, mobilenet_v3_large
from torchvision.transforms import v2 as T

REPO = Path(__file__).resolve().parents[2]
DATA = REPO / "ml" / "data" / "brands"
RUNS = REPO / "ml" / "runs" / "brand"
SIZE = 224
MEAN = [0.485, 0.456, 0.406]
STD = [0.229, 0.224, 0.225]


def transforms(train: bool):
    common = [T.ToImage(), T.ToDtype(torch.float32, scale=True), T.Normalize(MEAN, STD)]
    if not train:
        # The app squashes the full frame to the input size; do the same.
        return T.Compose([T.Resize((SIZE, SIZE), antialias=True), *common])
    return T.Compose([
        T.RandomResizedCrop(SIZE, scale=(0.6, 1.0), ratio=(0.6, 1.8), antialias=True),
        T.RandomHorizontalFlip(),
        T.ColorJitter(0.3, 0.3, 0.3, 0.05),
        T.RandomGrayscale(0.05),
        *common,
        T.RandomErasing(p=0.25, scale=(0.01, 0.06), value=0),  # extra black boxes, like masks
    ])


def build_model(num_classes: int, pretrained: bool = True) -> nn.Module:
    weights = MobileNet_V3_Large_Weights.IMAGENET1K_V2 if pretrained else None
    model = mobilenet_v3_large(weights=weights)
    model.classifier[3] = nn.Linear(model.classifier[3].in_features, num_classes)
    return model


@torch.no_grad()
def predict(model, loader, device) -> tuple[np.ndarray, np.ndarray]:
    model.eval()
    probs, labels = [], []
    for x, y in loader:
        with torch.autocast(device.type, enabled=device.type == "cuda"):
            logits = model(x.to(device, non_blocking=True))
        probs.append(torch.softmax(logits.float(), 1).cpu().numpy())
        labels.append(y.numpy())
    return np.concatenate(probs), np.concatenate(labels)


def summarize(probs: np.ndarray, labels: np.ndarray, min_conf: float) -> dict:
    top = probs.argsort(1)[:, ::-1]
    top1 = top[:, 0] == labels
    top3 = (top[:, :3] == labels[:, None]).any(1)
    answered = probs.max(1) >= min_conf
    return {
        "images": int(len(labels)),
        "top1": float(top1.mean()),
        "top3": float(top3.mean()),
        "answered_rate": float(answered.mean()),
        "accuracy_when_answered": float(top1[answered].mean()) if answered.any() else 0.0,
        "min_confidence": min_conf,
    }


class Exportable(nn.Module):
    """Input [1, 3, 224, 224] RGB 0..255 -> output [1, classes] probabilities."""

    def __init__(self, model: nn.Module):
        super().__init__()
        self.model = model.eval()
        self.register_buffer("mean", torch.tensor(MEAN).view(1, 3, 1, 1) * 255)
        self.register_buffer("std", torch.tensor(STD).view(1, 3, 1, 1) * 255)

    def forward(self, x):
        return torch.softmax(self.model((x - self.mean) / self.std), dim=1)


def export(labels: list[str]) -> None:
    model = build_model(len(labels), pretrained=False)
    model.load_state_dict(torch.load(RUNS / "best.pt", map_location="cpu"))
    wrapper = Exportable(model).eval()
    sample = torch.rand(1, 3, SIZE, SIZE) * 255
    with torch.no_grad():
        probs = wrapper(sample)
    out = RUNS / "brand_classifier.onnx"
    torch.onnx.export(wrapper, (sample,), str(out), input_names=["image"],
                      output_names=["probabilities"], opset_version=17, dynamo=False)
    np.savez(out.with_suffix(".reference.npz"), image=sample.numpy(), probs=probs.numpy())
    print(f"wrote {out}")


def main() -> int:
    global DATA, RUNS
    p = argparse.ArgumentParser()
    p.add_argument("--epochs", type=int, default=30)
    p.add_argument("--batch", type=int, default=64)
    p.add_argument("--lr", type=float, default=1e-3)
    p.add_argument("--workers", type=int, default=8)
    p.add_argument("--min-confidence", type=float, default=0.6)
    p.add_argument("--export", action="store_true", help="only export best.pt to ONNX")
    p.add_argument("--data", type=Path, default=DATA)
    p.add_argument("--runs", type=Path, default=RUNS)
    args = p.parse_args()
    DATA, RUNS = args.data, args.runs
    RUNS.mkdir(parents=True, exist_ok=True)

    train_ds = datasets.ImageFolder(DATA / "train", transforms(True))
    labels = train_ds.classes
    if args.export:
        export((RUNS / "labels.txt").read_text(encoding="utf-8").splitlines())
        return 0
    val_ds = datasets.ImageFolder(DATA / "val", transforms(False))
    test_ds = datasets.ImageFolder(DATA / "test", transforms(False))
    assert val_ds.classes == labels == test_ds.classes, "splits must have the same brands"
    (RUNS / "labels.txt").write_text("\n".join(labels) + "\n", encoding="utf-8")

    counts = Counter(train_ds.targets)
    print(f"{len(labels)} brands, train {len(train_ds)}, val {len(val_ds)}, test {len(test_ds)}")
    print("smallest classes:", sorted(((counts[i], labels[i]) for i in counts))[:5], flush=True)
    # Balance brands: each batch sees every brand about equally often.
    sample_w = [1.0 / counts[t] for t in train_ds.targets]
    sampler = WeightedRandomSampler(sample_w, num_samples=len(train_ds), replacement=True)

    kw = dict(num_workers=args.workers, pin_memory=True, persistent_workers=args.workers > 0)
    train_dl = DataLoader(train_ds, args.batch, sampler=sampler, drop_last=True, **kw)
    val_dl = DataLoader(val_ds, 128, **kw)
    test_dl = DataLoader(test_ds, 128, **kw)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = build_model(len(labels)).to(device)
    head = list(model.classifier.parameters())
    head_ids = {id(p) for p in head}
    body = [p for p in model.parameters() if id(p) not in head_ids]
    opt = torch.optim.AdamW([{"params": body, "lr": args.lr * 0.3}, {"params": head, "lr": args.lr}],
                            weight_decay=0.05)
    steps = args.epochs * len(train_dl)
    sched = torch.optim.lr_scheduler.OneCycleLR(
        opt, max_lr=[args.lr * 0.3, args.lr], total_steps=steps, pct_start=0.1)
    scaler = torch.amp.GradScaler(enabled=device.type == "cuda")
    loss_fn = nn.CrossEntropyLoss(label_smoothing=0.1)

    best = -1.0
    for epoch in range(1, args.epochs + 1):
        model.train()
        t0, total = time.time(), 0.0
        for x, y in train_dl:
            x, y = x.to(device, non_blocking=True), y.to(device, non_blocking=True)
            with torch.autocast(device.type, enabled=device.type == "cuda"):
                loss = loss_fn(model(x), y)
            opt.zero_grad(set_to_none=True)
            scaler.scale(loss).backward()
            scaler.step(opt)
            scaler.update()
            sched.step()
            total += loss.item()
        val = summarize(*predict(model, val_dl, device), args.min_confidence)
        if val["top1"] > best:
            best = val["top1"]
            torch.save(model.state_dict(), RUNS / "best.pt")
        print(f"epoch {epoch:3}/{args.epochs} loss {total / len(train_dl):.3f} "
              f"val top1 {val['top1']:.3f} top3 {val['top3']:.3f} "
              f"answered {val['answered_rate']:.2f} acc@answered {val['accuracy_when_answered']:.3f} "
              f"{time.time() - t0:.0f}s", flush=True)

    model.load_state_dict(torch.load(RUNS / "best.pt", map_location=device))
    test = summarize(*predict(model, test_dl, device), args.min_confidence)
    metrics = {"labels": labels, "val_best_top1": best, "test": test}
    (RUNS / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    print("TEST:", json.dumps(test), flush=True)
    export(labels)
    return 0


if __name__ == "__main__":
    sys.exit(main())
