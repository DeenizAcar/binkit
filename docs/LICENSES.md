# Third-party licenses

Every dependency, pretrained model and dataset used by Bink It is listed here **before** it is added.

Allowed: permissive licenses (Apache-2.0, MIT, BSD).
Not allowed: AGPL / GPL (this rules out Ultralytics YOLOv5/v8/v11 and their derivatives).

## App dependencies (Flutter)

| Package | Version | License | Purpose |
|---|---|---|---|
| [camera](https://pub.dev/packages/camera) | ^0.12.0+2 | BSD-3-Clause | Camera preview and frame capture (Android: CameraX) |
| [tflite_flutter](https://pub.dev/packages/tflite_flutter) | ^0.12.1 | Apache-2.0 | On-device TensorFlow Lite inference (bundles the TFLite runtime, Apache-2.0) |
| [image](https://pub.dev/packages/image) | ^4.13.1 | MIT | Crop, resize, blur / mask plate regions in memory |
| [cupertino_icons](https://pub.dev/packages/cupertino_icons) | ^1.0.8 | MIT | Flutter template default |

Transitive dependencies (checked 2026-11-25 from `pubspec.lock`): all BSD, MIT or Apache-2.0. No GPL/AGPL.

> Note: the plugins pull in extra permissions: `RECORD_AUDIO`, `WRITE_EXTERNAL_STORAGE`
> (camera_android_camerax), `ACCESS_NETWORK_STATE` (androidx.media3), and implied
> `READ_EXTERNAL_STORAGE` / `READ_PHONE_STATE` (LiteRT GPU API, old targetSdk).
> All are removed in `app/android/app/src/main/AndroidManifest.xml` (`tools:node="remove"`),
> so the release build only requests `CAMERA`. (`INTERNET` appears in debug builds only,
> for Flutter tooling.) Re-check the merged manifest whenever a dependency changes.

## Pretrained models

| Model | Source | License | Used for |
|---|---|---|---|
| — | — | — | — |

## Datasets

| Dataset | License / terms | Commercial use | Used in shipped model? |
|---|---|---|---|
| Stanford Cars | Non-commercial research only | No | **No** (local experiments only) |
| CompCars | Non-commercial research only | No | **No** (local experiments only) |
