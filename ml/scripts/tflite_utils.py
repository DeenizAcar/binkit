"""Shared ONNX -> TFLite helpers (conversion venv)."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image


def load_interpreter(path: Path):
    try:
        from ai_edge_litert.interpreter import Interpreter
    except ImportError:
        from tensorflow.lite import Interpreter  # type: ignore
    interp = Interpreter(model_path=str(path))
    interp.allocate_tensors()
    return interp


def onnx_to_tflite(onnx_path: Path, work_dir: Path, sample_images: list[Path]) -> tuple[Path, Path]:
    """Runs onnx2tf; returns (float32, float16) TFLite paths.

    onnx2tf wants 20 sample images for its internal checks and would otherwise
    download them from the internet, so they are built from our own data.
    """
    out_dir = work_dir / "tflite"
    if out_dir.exists():
        shutil.rmtree(out_dir)
    sample_file = work_dir / "calibration_image_sample_data_20x128x128x3_float32.npy"
    if not sample_file.exists():
        arr = np.stack([np.asarray(Image.open(i).convert("RGB").resize((128, 128)), np.float32) / 255.0
                        for i in sample_images[:20]])
        np.save(sample_file, arr)
    env = {**os.environ,  # so onnx2tf finds the onnxsim CLI next to this python
           "PATH": str(Path(sys.executable).parent) + os.pathsep + os.environ["PATH"]}
    subprocess.run([sys.executable, "-m", "onnx2tf", "-i", str(onnx_path.resolve()),
                    "-o", str(out_dir), "-osd"], check=True, cwd=work_dir, env=env)
    return next(out_dir.glob("*_float32.tflite")), next(out_dir.glob("*_float16.tflite"))
