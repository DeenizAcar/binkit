# ML

Model training for Bink It. Training runs in free Google Colab; outputs are `.tflite`
files (int8 or float16) copied into `app/assets/models/`.

## Models

| Model | Purpose | Architecture | License | Status |
|---|---|---|---|---|
| `plate_detector.tflite` | License plate **location only** (bounding boxes, no OCR) | TBD (permissive license, e.g. YOLOX) | — | not started |
| `car_classifier.tflite` | Car make classification (~30–40 brands), top-3 + scores | TBD (e.g. EfficientNet-Lite / MobileNet) | — | not started |

## Data rules

- Stanford Cars and CompCars are **non-commercial only**: local experiments only, never used to train a shipped model.
- No scraping that violates a site's terms of use.
- Datasets live outside git (`ml/data/`, `ml/datasets/` are ignored).

## Evaluation results

Accuracy claims are only made after measuring on a separate held-out test set. Record each result here.

| Date | Model | Version | Test set | Metric | Result |
|---|---|---|---|---|---|
| — | — | — | — | — | — |
