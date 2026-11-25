"""Export the trained plate detector to ONNX with the app's output contract.

Run in the CUDA/torch venv:
  ml/.venv-torch/Scripts/python.exe -I ml/scripts/export_plate_detector.py [--weights ml/runs/plate/best.pt]

Then convert in the conversion venv:
  ml/.venv-convert/Scripts/python.exe -I ml/scripts/convert_plate_detector.py

The exported graph:
  input  [1, 3, 320, 320] float32, RGB 0..255 (onnx2tf turns this into NHWC [1, 320, 320, 3])
  output boxes  [1, N, 4] (ymin, xmin, ymax, xmax), normalized 0..1, decoded from anchors
         scores [1, N]    plate probability
No NMS in the graph: the app runs NMS in Dart.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import torch
from torch import nn
from torchvision.models.detection.image_list import ImageList

sys.path.insert(0, str(Path(__file__).resolve().parent))
from train_plate_detector import INPUT_SIZE, RUNS, build_model  # noqa: E402


class ExportablePlateDetector(nn.Module):
    def __init__(self, model: nn.Module):
        super().__init__()
        model.eval()
        self.backbone = model.backbone
        self.head = model.head
        self.box_coder = model.box_coder
        mean = torch.tensor(model.transform.image_mean).view(1, 3, 1, 1)
        std = torch.tensor(model.transform.image_std).view(1, 3, 1, 1)
        self.register_buffer("mean", mean * 255.0)
        self.register_buffer("std", std * 255.0)
        with torch.no_grad():
            dummy = torch.zeros(1, 3, INPUT_SIZE, INPUT_SIZE)
            images = ImageList(dummy, [(INPUT_SIZE, INPUT_SIZE)])
            feats = list(model.backbone(dummy).values())
            anchors = model.anchor_generator(images, feats)[0]  # [N, 4] xyxy pixels
        self.register_buffer("anchors", anchors)
        # Anchor centers/sizes, precomputed so decoding is plain slicing + math
        # (no split/unbind ops, which become Flex ops in TFLite).
        wh = anchors[:, 2:4] - anchors[:, 0:2]
        self.register_buffer("anchor_ctr", anchors[:, 0:2] + 0.5 * wh)  # [N, 2] (x, y)
        self.register_buffer("anchor_wh", wh)                           # [N, 2] (w, h)
        wx, wy, ww, wh_ = model.box_coder.weights
        self.register_buffer("weights", torch.tensor([wx, wy, ww, wh_], dtype=torch.float32))
        self.clip = float(model.box_coder.bbox_xform_clip)

    def forward(self, x: torch.Tensor):
        x = (x - self.mean) / self.std
        feats = list(self.backbone(x).values())
        out = self.head(feats)
        reg = out["bbox_regression"][0]
        logits = out["cls_logits"][0]
        reg = reg / self.weights                              # [N, 4] dx, dy, dw, dh
        ctr = reg[:, 0:2] * self.anchor_wh + self.anchor_ctr  # [N, 2] (x, y)
        size = torch.exp(torch.clamp(reg[:, 2:4], max=self.clip)) * self.anchor_wh
        xy1 = (ctr - 0.5 * size) / INPUT_SIZE
        xy2 = (ctr + 0.5 * size) / INPUT_SIZE
        boxes = torch.cat([xy1[:, 1:2], xy1[:, 0:1], xy2[:, 1:2], xy2[:, 0:1]], dim=1)
        boxes = torch.clamp(boxes, 0.0, 1.0)                  # ymin, xmin, ymax, xmax
        scores = torch.softmax(logits, dim=-1)[:, 1]
        return boxes.unsqueeze(0), scores.unsqueeze(0)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--weights", type=Path, default=RUNS / "best.pt")
    p.add_argument("--out", type=Path, default=RUNS / "plate_detector.onnx")
    args = p.parse_args()

    model = build_model(pretrained=False)
    model.load_state_dict(torch.load(args.weights, map_location="cpu"))
    wrapper = ExportablePlateDetector(model).eval()

    sample = torch.rand(1, 3, INPUT_SIZE, INPUT_SIZE) * 255
    with torch.no_grad():
        boxes, scores = wrapper(sample)
        # Check the hand-written decoder against torchvision's.
        x = (sample - wrapper.mean) / wrapper.std
        reg = wrapper.head(list(wrapper.backbone(x).values()))["bbox_regression"][0]
        ref = wrapper.box_coder.decode_single(reg, wrapper.anchors).clamp(0, INPUT_SIZE) / INPUT_SIZE
        ref = ref[:, [1, 0, 3, 2]]
        diff = (ref - boxes[0]).abs().max().item()
        print(f"decoder check: max diff vs torchvision {diff:.2e}")
        assert diff < 1e-4, "decoder mismatch"
    torch.onnx.export(
        wrapper, (sample,), str(args.out),
        input_names=["image"], output_names=["boxes", "scores"],
        opset_version=17, dynamo=False,
    )
    # Reference output so the converter can check the TFLite model matches.
    np.savez(args.out.with_suffix(".reference.npz"),
             image=sample.numpy(), boxes=boxes.numpy(), scores=scores.numpy())
    print(f"wrote {args.out} (anchors: {wrapper.anchors.shape[0]})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
