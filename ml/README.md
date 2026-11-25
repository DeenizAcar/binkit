# ML

Model training for Bink It. Training runs in free Google Colab; outputs are `.tflite`
files (int8 or float16) copied into `app/assets/models/`.

## Models

| Model | Purpose | Architecture | License | Status |
|---|---|---|---|---|
| `plate_detector.tflite` | License plate **location only** (bounding boxes, no OCR) | SSDLite320-MobileNetV3-Large (torchvision) | BSD-3-Clause; data: Open Images (CC BY 4.0 / CC BY 2.0) | training |
| `car_classifier.tflite` | Car make classification (~30–40 brands), top-3 + scores | TBD (e.g. EfficientNet-Lite / MobileNet) | — | not started |

## Model contracts (what the app expects)

Both models get the **full frame resized (not cropped) to the input size**, RGB,
pixel values **0..255**. Any normalization (e.g. `/255` or `(x-127.5)/127.5`) must be
**inside the model**. Train/evaluate with the same squash resize.
Input tensor: `[1, h, w, 3]`, type float32, uint8 or int8 (quantization params are read from the model).

**`plate_detector.tflite`**: location only, no text.
- Current model: torchvision SSDLite320-MobileNetV3-Large, input `[1, 320, 320, 3]` float32.
- 2 outputs (any order): `boxes [1, N, 4]` as `(ymin, xmin, ymax, xmax)` normalized 0..1, already decoded
  from anchors, and `scores [1, N]`, one per anchor (N = 3234). **No NMS in the model**: the app runs greedy NMS
  (score >= 0.1, IoU 0.5, max 20 boxes); `convert_plate_detector.py` evaluates with the identical NMS.
- The app also still accepts the TF Object Detection API 4-output layout (`boxes, classes, scores, count`).
- App thresholds: `app/lib/config/scan_config.dart` (score >= 0.4 counts as a plate; >15% of frame → scan rejected).

Plate detector pipeline (local GPU, see `ml/DATASETS.md` for why not Colab/TF OD API):
```
ml/.venv-torch/Scripts/python.exe -I ml/scripts/fetch_openimages_plates.py
ml/.venv-torch/Scripts/python.exe -I ml/scripts/train_plate_detector.py --epochs 40
ml/.venv-torch/Scripts/python.exe -I ml/scripts/export_plate_detector.py          # -> ONNX
ml/.venv-convert/Scripts/python.exe -I ml/scripts/convert_plate_detector.py --install  # -> TFLite, test-set eval
```
Venvs (git-ignored): `.venv-torch` = Python 3.11, torch/torchvision (CUDA 12.8), pillow, onnx;
`.venv-convert` = Python 3.11, tensorflow 2.19, tf-keras, onnx2tf, onnx, onnxruntime, onnxsim, onnx-graphsurgeon,
sng4onnx, simple_onnx_processing_tools.

**`car_classifier.tflite`** + **`labels.txt`**
- Output `[1, numLabels]` probabilities (softmax inside the model).
- `labels.txt`: one brand per line, same order as the output; line count must equal `numLabels`
  or the app refuses to load the model.
- App shows "not sure" when top-1 < 0.6.

Without both models the app fails closed: it never classifies an unmasked frame.

**Train the classifier on plate-masked images.** In the app the classifier only ever sees frames
whose plates are painted black, so training images must be masked the same way (with the plate
detector, solid black, same margin) or train and inference data won't match.

## Building the brand image set

```
python -I ml/scripts/fetch_commons.py check                       # verify Commons categories
python -I ml/scripts/fetch_commons.py fetch --per-brand 400       # PD / CC0 / CC BY only
# ...manually delete wrong images in ml/data/commons/<brand>/...
python -I ml/scripts/fetch_commons.py credits                     # regenerate app credits
```

## Data rules

- Stanford Cars and CompCars are **non-commercial only**: local experiments only, never used to train a shipped model.
- No scraping that violates a site's terms of use.
- Datasets live outside git (`ml/data/`, `ml/datasets/` are ignored).

## Evaluation results

Accuracy claims are only made after measuring on a separate held-out test set. Record each result here.

| Date | Model | Version | Test set | Metric | Result |
|---|---|---|---|---|---|
| — | — | — | — | — | — |
