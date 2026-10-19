# Gesture model training results (T4.0, ADDENDUM-03)

Run by the monitor on Google Colab (Tesla T4), 2026-10-19, notebook `training/gesture_yolo.ipynb` (M-007 fixed version). Copied from the notebook's saved outputs in Drive (cell 5 log and prep report). Numbers are exact as printed by Ultralytics.

Environment: ultralytics 8.4.182, torch 2.11.0+cu130, Python 3.13.15, Tesla T4. Model: YOLO26n (121 layers fused, 2,390,950 parameters, 5.4 GFLOPs), imgsz 416, 40 of 40 epochs.

## Data (prep_report.json)
Dataset `cj-mills/hagrid-sample-120k-384p` (CC BY-SA 4.0), 800 images per gesture class, split by HaGRID subject (`user_id`), seed 42. Skipped: `{'no_image': 12059}` (annotations without an image in the sample).

| Split | Images | Subjects | palm | one | peace | three | four | no_gesture |
|---|---|---|---|---|---|---|---|---|
| train | 3200 | 1674 | 640 | 640 | 640 | 640 | 640 | 748 |
| val | 400 | 209 | 80 | 80 | 80 | 80 | 80 | 95 |
| test | 400 | 210 | 80 | 80 | 80 | 80 | 80 | 75 |

## Held-out test split (400 images, 475 boxes)
COCO-pretrained weights have no gesture classes, so their gesture mAP is not measured. The baseline is one epoch of adaptation from `yolo26n.pt`.

| Model | Precision | Recall | mAP50 | mAP50-95 |
|---|---|---|---|---|
| Adaptation baseline, 1 epoch | 0.685 | 0.754 | 0.784 | 0.592 |
| Fine-tuned, 40 epochs | 0.970 | 0.961 | 0.988 | 0.844 |

### Fine-tuned, per class
| Class | Precision | Recall | mAP50 | mAP50-95 |
|---|---|---|---|---|
| palm | 0.975 | 0.993 | 0.995 | 0.897 |
| one | 0.988 | 0.997 | 0.995 | 0.870 |
| peace | 0.987 | 0.942 | 0.991 | 0.873 |
| three | 0.930 | 0.950 | 0.983 | 0.843 |
| four | 0.982 | 0.950 | 0.990 | 0.889 |
| no_gesture | 0.956 | 0.933 | 0.973 | 0.690 |

### Baseline, per class (1 epoch)
| Class | Precision | Recall | mAP50 | mAP50-95 |
|---|---|---|---|---|
| palm | 0.670 | 0.925 | 0.935 | 0.717 |
| one | 0.896 | 0.756 | 0.919 | 0.706 |
| peace | 0.689 | 0.747 | 0.821 | 0.650 |
| three | 0.691 | 0.487 | 0.681 | 0.524 |
| four | 0.469 | 0.900 | 0.610 | 0.496 |
| no_gesture | 0.696 | 0.707 | 0.738 | 0.461 |

## Exported ONNX (checked by the monitor on the demo laptop)
- File: `best.onnx` (9,760,136 bytes), installed at `backend/vision/weights/gesture.onnx` (gitignored, byte-identical copy).
- Input `images [1, 3, 416, 416]`; output `output0 [1, 10, 3549]` (4 box + 6 classes, classic head, `end2end=False` confirmed).
- Embedded names `{0: 'palm', 1: 'one', 2: 'peace', 3: 'three', 4: 'four', 5: 'no_gesture'}` (matches ADDENDUM-03).
- Laptop CPU (Ryzen 5 7520U, onnxruntime, 2 threads, random input, 30 runs): **p50 18.6 ms, p95 47.3 ms**. Target was under 120 ms. Real-frame latency with preprocessing still to be measured in T4.2.

## Caveats
- These are HaGRID test-set numbers (other people, other lighting). Venue accuracy (ADDENDUM-03 T4.4: 4 of 5 tries per gesture, two players) is not measured yet.
- The metrics-table and export cells' outputs were not yet saved to the Drive copy; the per-class numbers above come from the validation log in cell 5, which is the same evaluation.
