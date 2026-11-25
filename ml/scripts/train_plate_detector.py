"""Fine-tune torchvision SSDLite320-MobileNetV3 as a one-class plate detector.

Location boxes only; nothing here reads plate text.

Usage (from the repo root, CUDA venv):
  ml/.venv-torch/Scripts/python.exe -I ml/scripts/train_plate_detector.py --epochs 40

Data: ml/data/openimages_plates/{train,validation}/ (fetch_openimages_plates.py).
Output: ml/runs/plate/{last,best}.pt and metrics.csv (git-ignored).
"""

from __future__ import annotations

import argparse
import csv
import math
import sys
import time
from collections import defaultdict
from functools import partial
from pathlib import Path

import torch
from torch import nn
from torch.utils.data import DataLoader, Dataset
from torchvision import tv_tensors
from torchvision.io import ImageReadMode, decode_jpeg, read_file
from torchvision.models.detection import (
    SSDLite320_MobileNet_V3_Large_Weights,
    ssdlite320_mobilenet_v3_large,
)
from torchvision.models.detection import _utils as det_utils
from torchvision.models.detection.ssdlite import SSDLiteClassificationHead
from torchvision.ops import box_iou
from torchvision.transforms import v2 as T

REPO = Path(__file__).resolve().parents[2]
DATA = REPO / "ml" / "data" / "openimages_plates"
RUNS = REPO / "ml" / "runs" / "plate"
INPUT_SIZE = 320
NUM_CLASSES = 2  # background + plate


class PlateDataset(Dataset):
    def __init__(self, split: str, train: bool):
        self.dir = DATA / split / "images"
        boxes: dict[str, list] = defaultdict(list)
        with (DATA / split / "boxes.csv").open(encoding="utf-8") as f:
            for r in csv.DictReader(f):
                boxes[r["image_id"]].append([float(r[k]) for k in ("xmin", "ymin", "xmax", "ymax")])
        self.ids = sorted(i for i in boxes if (self.dir / f"{i}.jpg").exists())
        self.boxes = boxes
        self.transform = (
            T.Compose([
                T.RandomPhotometricDistort(p=0.5),
                T.RandomZoomOut(fill=114, side_range=(1.0, 2.5), p=0.4),
                T.RandomIoUCrop(),
                T.RandomHorizontalFlip(),
                T.SanitizeBoundingBoxes(min_size=2),
                T.ToDtype(torch.float32, scale=True),
            ])
            if train
            else T.ToDtype(torch.float32, scale=True)
        )

    def __len__(self) -> int:
        return len(self.ids)

    def __getitem__(self, idx: int):
        image_id = self.ids[idx]
        img = decode_jpeg(read_file(str(self.dir / f"{image_id}.jpg")), mode=ImageReadMode.RGB)
        h, w = img.shape[-2:]
        b = torch.tensor(self.boxes[image_id], dtype=torch.float32)
        b = b * torch.tensor([w, h, w, h])
        target = {
            "boxes": tv_tensors.BoundingBoxes(b, format="XYXY", canvas_size=(h, w)),
            "labels": torch.ones(len(b), dtype=torch.int64),
        }
        img, target = self.transform(tv_tensors.Image(img), target)
        return img, target


def collate(batch):
    return tuple(zip(*batch))


def build_model(pretrained: bool = True) -> nn.Module:
    if pretrained:
        model = ssdlite320_mobilenet_v3_large(weights=SSDLite320_MobileNet_V3_Large_Weights.COCO_V1)
    else:
        # weights_backbone=None keeps the same (reduced-tail) architecture as the
        # COCO model, so saved checkpoints load; it also avoids a download.
        model = ssdlite320_mobilenet_v3_large(weights=None, weights_backbone=None)
    in_channels = det_utils.retrieve_out_channels(model.backbone, (INPUT_SIZE, INPUT_SIZE))
    num_anchors = model.anchor_generator.num_anchors_per_location()
    norm_layer = partial(nn.BatchNorm2d, eps=0.001, momentum=0.03)
    model.head.classification_head = SSDLiteClassificationHead(
        in_channels, num_anchors, NUM_CLASSES, norm_layer)
    # Keep low-score boxes for evaluation; the app applies its own threshold.
    model.score_thresh = 0.05
    model.detections_per_img = 50
    return model


def average_precision(preds, targets, iou_thr: float = 0.5) -> tuple[float, float]:
    """VOC-style AP@iou_thr and recall at score >= 0.4 for a single class."""
    scored = []  # (score, is_true_positive)
    n_gt = 0
    recalled = 0
    for p, t in zip(preds, targets):
        gt = t["boxes"]
        n_gt += len(gt)
        matched = torch.zeros(len(gt), dtype=torch.bool)
        order = p["scores"].argsort(descending=True)
        ious = box_iou(p["boxes"][order], gt) if len(gt) and len(order) else None
        for k, idx in enumerate(order):
            tp = False
            if ious is not None:
                best_iou, j = ious[k].max(0)
                if best_iou >= iou_thr and not matched[j]:
                    matched[j] = True
                    tp = True
                    if p["scores"][idx] >= 0.4:
                        recalled += 1
            scored.append((float(p["scores"][idx]), tp))
    if n_gt == 0:
        return 0.0, 0.0
    scored.sort(key=lambda x: -x[0])
    tp_cum = fp_cum = 0
    precisions, recalls = [], []
    for _, tp in scored:
        tp_cum += tp
        fp_cum += not tp
        precisions.append(tp_cum / (tp_cum + fp_cum))
        recalls.append(tp_cum / n_gt)
    # All-point interpolation.
    ap, prev_r = 0.0, 0.0
    for i in range(len(precisions)):
        p_max = max(precisions[i:])
        ap += (recalls[i] - prev_r) * p_max
        prev_r = recalls[i]
    return ap, recalled / n_gt


@torch.no_grad()
def evaluate(model, loader, device) -> tuple[float, float]:
    model.eval()
    preds, targets = [], []
    for imgs, tgts in loader:
        out = model([i.to(device) for i in imgs])
        preds += [{k: v.cpu() for k, v in o.items()} for o in out]
        targets += [{"boxes": t["boxes"].as_subclass(torch.Tensor)} for t in tgts]
    return average_precision(preds, targets)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--epochs", type=int, default=40)
    p.add_argument("--batch", type=int, default=32)
    p.add_argument("--lr", type=float, default=0.02)
    p.add_argument("--workers", type=int, default=6)
    p.add_argument("--eval-every", type=int, default=2)
    p.add_argument("--train-split", default="train", help="for smoke tests only")
    p.add_argument("--out", type=Path, default=RUNS)
    args = p.parse_args()

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"device: {device}", flush=True)
    runs = args.out
    runs.mkdir(parents=True, exist_ok=True)

    train_ds = PlateDataset(args.train_split, train=True)
    val_ds = PlateDataset("validation", train=False)
    print(f"train {len(train_ds)} images, validation {len(val_ds)} images", flush=True)
    train_dl = DataLoader(train_ds, args.batch, shuffle=True, num_workers=args.workers,
                          collate_fn=collate, persistent_workers=args.workers > 0, drop_last=True)
    val_dl = DataLoader(val_ds, 16, num_workers=args.workers, collate_fn=collate)

    model = build_model().to(device)
    params = [p for p in model.parameters() if p.requires_grad]
    opt = torch.optim.SGD(params, lr=args.lr, momentum=0.9, weight_decay=4e-5)
    steps = args.epochs * len(train_dl)
    warmup = min(500, steps // 10)
    sched = torch.optim.lr_scheduler.LambdaLR(
        opt, lambda s: (s + 1) / warmup if s < warmup
        else 0.5 * (1 + math.cos(math.pi * (s - warmup) / max(1, steps - warmup))))

    best_ap = -1.0
    log_path = runs / "metrics.csv"
    with log_path.open("w", newline="") as f:
        csv.writer(f).writerow(["epoch", "loss", "val_ap50", "val_recall@0.4", "seconds"])

    for epoch in range(1, args.epochs + 1):
        model.train()
        t0 = time.time()
        total = 0.0
        for imgs, tgts in train_dl:
            imgs = [i.to(device, non_blocking=True) for i in imgs]
            tgts = [{"boxes": t["boxes"].as_subclass(torch.Tensor).to(device),
                     "labels": t["labels"].to(device)} for t in tgts]
            losses = model(imgs, tgts)
            loss = sum(losses.values())
            if not torch.isfinite(loss):
                print("non-finite loss, skipping batch", flush=True)
                opt.zero_grad()
                continue
            opt.zero_grad()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(params, 10.0)
            opt.step()
            sched.step()
            total += loss.item()
        mean_loss = total / len(train_dl)

        ap = rec = float("nan")
        if epoch % args.eval_every == 0 or epoch == args.epochs:
            ap, rec = evaluate(model, val_dl, device)
            if ap > best_ap:
                best_ap = ap
                torch.save(model.state_dict(), runs / "best.pt")
        torch.save(model.state_dict(), runs / "last.pt")
        secs = time.time() - t0
        print(f"epoch {epoch:3}/{args.epochs}  loss {mean_loss:.4f}  val AP50 {ap:.4f}  "
              f"recall@0.4 {rec:.4f}  {secs:.0f}s", flush=True)
        with log_path.open("a", newline="") as f:
            csv.writer(f).writerow([epoch, f"{mean_loss:.4f}", f"{ap:.4f}", f"{rec:.4f}", f"{secs:.0f}"])

    print(f"best validation AP50: {best_ap:.4f}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
