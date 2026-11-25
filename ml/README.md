# ML

Model training for Bink It. Training runs in free Google Colab; outputs are `.tflite`
files (int8 or float16) copied into `app/assets/models/`.

## Models

| Model | Purpose | Architecture | License | Status |
|---|---|---|---|---|
| `plate_detector.tflite` | License plate **location only** (bounding boxes, no OCR) | TBD (permissive license, e.g. YOLOX) | — | not started |
| `car_classifier.tflite` | Car make classification (~30–40 brands), top-3 + scores | TBD (e.g. EfficientNet-Lite / MobileNet) | — | not started |

## Model contracts (what the app expects)

Both models get the **full frame resized (not cropped) to the input size**, RGB,
pixel values **0..255**. Any normalization (e.g. `/255` or `(x-127.5)/127.5`) must be
**inside the model**. Train/evaluate with the same squash resize.
Input tensor: `[1, h, w, 3]`, type float32, uint8 or int8 (quantization params are read from the model).

**`plate_detector.tflite`**: location only, no text.
- Either 2 outputs: `boxes [1, N, 4]` as `(ymin, xmin, ymax, xmax)` normalized 0..1, `scores [1, N]`,
- or 4 outputs in TF Object Detection API order: `boxes, classes, scores, count`.
- NMS must be done inside the model (or the export).
- App thresholds: `app/lib/config/scan_config.dart` (score >= 0.4 counts as a plate; >15% of frame → scan rejected).

**`car_classifier.tflite`** + **`labels.txt`**
- Output `[1, numLabels]` probabilities (softmax inside the model).
- `labels.txt`: one brand per line, same order as the output; line count must equal `numLabels`
  or the app refuses to load the model.
- App shows "not sure" when top-1 < 0.6.

Without both models the app fails closed: it never classifies an unmasked frame.

## Data rules

- Stanford Cars and CompCars are **non-commercial only**: local experiments only, never used to train a shipped model.
- No scraping that violates a site's terms of use.
- Datasets live outside git (`ml/data/`, `ml/datasets/` are ignored).

## Evaluation results

Accuracy claims are only made after measuring on a separate held-out test set. Record each result here.

| Date | Model | Version | Test set | Metric | Result |
|---|---|---|---|---|---|
| — | — | — | — | — | — |
