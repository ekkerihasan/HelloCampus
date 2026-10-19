"""Generates gesture_yolo.ipynb from the cells below, so the notebook stays reviewable as plain Python.
Run: python training/build_notebook.py"""
import json
from pathlib import Path

CELLS: list[tuple[str, str]] = [
    ("md", """# Hello Campus: gesture detector (YOLO26n)

One detection model whose classes are the gestures: `palm`, `like`, `dislike`, `ok`, `peace`, `no_gesture`.

Steps: dataset prep (HaGRID subset + team frames), train, evaluate baseline vs fine-tuned, export ONNX, measure latency.

**Dataset license:** HaGRID is released under CC BY-SA 4.0 (check the current license on https://github.com/hukenovs/hagrid and record it in the project README).

Runtime: GPU (Runtime > Change runtime type > T4)."""),
    ("code", """!pip -q install -U ultralytics onnx onnxruntime pyyaml"""),
    ("md", """## 1. Config
Set `HAGRID_ROOT` to a folder containing HaGRID images and annotations. Get the download links for the
per-class archives and annotations from the HaGRID README (we do not hardcode them here, they change between releases).
Expected layout after download and unzip:
```
HAGRID_ROOT/
  images/<class>/<image_id>.jpg      (one folder per gesture class)
  annotations/<split>/<class>.json   (or annotations/<class>.json)
```
Team frames: upload `training/own_frames/<class>/*.jpg` with YOLO label files `*.txt` next to them (label with Roboflow, CVAT or Label Studio)."""),
    ("code", """from pathlib import Path
CLASSES = ["palm", "like", "dislike", "ok", "peace", "no_gesture"]
GESTURE_CLASSES = CLASSES[:-1]           # folders to sample images from
PER_CLASS = 800                          # images sampled per gesture class
SPLIT = (0.8, 0.1, 0.1)
SEED = 42
IMGSZ = 416
EPOCHS = 50
PATIENCE = 10

HAGRID_ROOT = Path("/content/hagrid")    # change me
OWN_FRAMES = Path("/content/own_frames") # change me (optional)
OUT = Path("/content/gesture_ds")"""),
    ("md", "## 2. Convert HaGRID annotations to YOLO format and split"),
    ("code", """import json, random, shutil
from collections import Counter

random.seed(SEED)
cls_id = {c: i for i, c in enumerate(CLASSES)}

def load_annotations(cls):
    paths = list(HAGRID_ROOT.glob(f"annotations/**/{cls}.json"))
    ann = {}
    for p in paths:
        ann.update(json.loads(p.read_text()))
    return ann

def find_image(cls, image_id):
    for ext in (".jpg", ".jpeg", ".png"):
        hits = list(HAGRID_ROOT.glob(f"**/{cls}/{image_id}{ext}"))
        if hits:
            return hits[0]
    return None

def yolo_lines(entry):
    # HaGRID boxes are normalized [x_top_left, y_top_left, w, h]; other gestures' boxes are dropped.
    lines = []
    for (x, y, w, h), label in zip(entry["bboxes"], entry["labels"]):
        if label not in cls_id:
            continue
        lines.append(f"{cls_id[label]} {x + w / 2:.6f} {y + h / 2:.6f} {w:.6f} {h:.6f}")
    return lines

if OUT.exists():
    shutil.rmtree(OUT)
samples = []  # (image_path, label_lines)
for cls in GESTURE_CLASSES:
    ann = load_annotations(cls)
    ids = list(ann)
    random.shuffle(ids)
    taken = 0
    for image_id in ids:
        if taken >= PER_CLASS:
            break
        img = find_image(cls, image_id)
        lines = yolo_lines(ann[image_id])
        if img is None or not lines:
            continue
        samples.append((img, lines))
        taken += 1
    print(f"{cls}: {taken} images")

# Team frames from the venue, YOLO .txt labels next to each image
for img in sorted(OWN_FRAMES.glob("**/*.jpg")) if OWN_FRAMES.exists() else []:
    txt = img.with_suffix(".txt")
    if txt.exists():
        samples.append((img, txt.read_text().strip().splitlines()))

random.shuffle(samples)
n = len(samples)
cut1, cut2 = int(n * SPLIT[0]), int(n * (SPLIT[0] + SPLIT[1]))
splits = {"train": samples[:cut1], "val": samples[cut1:cut2], "test": samples[cut2:]}

for split, items in splits.items():
    (OUT / split / "images").mkdir(parents=True, exist_ok=True)
    (OUT / split / "labels").mkdir(parents=True, exist_ok=True)
    for i, (img, lines) in enumerate(items):
        stem = f"{split}_{i:05d}"
        shutil.copy(img, OUT / split / "images" / f"{stem}{img.suffix}")
        (OUT / split / "labels" / f"{stem}.txt").write_text("\\n".join(lines) + "\\n")

# T0.3 acceptance: class counts per split
for split, items in splits.items():
    counts = Counter(CLASSES[int(l.split()[0])] for _, lines in items for l in lines)
    print(split, len(items), "images |", {c: counts.get(c, 0) for c in CLASSES})

import yaml
(OUT / "data.yaml").write_text(yaml.safe_dump({
    "path": str(OUT), "train": "train/images", "val": "val/images", "test": "test/images",
    "names": {i: c for i, c in enumerate(CLASSES)},
}))"""),
    ("md", """## 3. Baseline vs fine-tuned
COCO-pretrained YOLO26n has no gesture classes, so a true zero-shot baseline is mAP 0.
As the baseline we record a 1-epoch run (pretrained weights, new head barely trained) and compare it to the full fine-tune."""),
    ("code", """from ultralytics import YOLO

baseline = YOLO("yolo26n.pt")
baseline.train(data=str(OUT / "data.yaml"), imgsz=IMGSZ, epochs=1, seed=SEED, name="baseline", plots=False)
base_metrics = baseline.val(data=str(OUT / "data.yaml"), imgsz=IMGSZ, split="test")

model = YOLO("yolo26n.pt")
model.train(data=str(OUT / "data.yaml"), imgsz=IMGSZ, epochs=EPOCHS, patience=PATIENCE, seed=SEED, name="gesture")
ft_metrics = model.val(data=str(OUT / "data.yaml"), imgsz=IMGSZ, split="test")"""),
    ("code", """# Markdown table for README.md
def row(name, m):
    return f"| {name} | {m.box.map50:.3f} | {m.box.map:.3f} |"
print("| Model | mAP50 | mAP50-95 |\\n|---|---|---|")
print(row("Baseline (1 epoch)", base_metrics))
print(row("Fine-tuned", ft_metrics))
print("\\n| Class | Precision | Recall | AP50 |\\n|---|---|---|---|")
present = list(ft_metrics.box.ap_class_index)
for i, c in enumerate(CLASSES):
    p, r, ap50, ap = ft_metrics.box.class_result(present.index(i)) if i in present else (0, 0, 0, 0)
    print(f"| {c} | {p:.3f} | {r:.3f} | {ap50:.3f} |")"""),
    ("md", "## 4. Export ONNX and measure CPU latency"),
    ("code", """onnx_path = model.export(format="onnx", imgsz=IMGSZ, opset=17, simplify=True, dynamic=False)
print(onnx_path)

import time, numpy as np, onnxruntime as ort
sess = ort.InferenceSession(onnx_path, providers=["CPUExecutionProvider"])
x = np.random.rand(1, 3, IMGSZ, IMGSZ).astype(np.float32)
inp = sess.get_inputs()[0].name
for _ in range(5):
    sess.run(None, {inp: x})
t = time.perf_counter()
for _ in range(50):
    sess.run(None, {inp: x})
print(f"Colab CPU latency: {(time.perf_counter() - t) / 50 * 1000:.1f} ms/frame (re-measure on the demo laptop)")
print("output shape:", [o.shape for o in sess.get_outputs()])"""),
    ("code", """from google.colab import files
files.download(onnx_path)  # save as backend/vision/weights/gesture.onnx"""),
]


def build() -> dict:
    cells = []
    for kind, src in CELLS:
        cell = {"cell_type": "markdown" if kind == "md" else "code", "metadata": {}, "source": src.splitlines(keepends=True)}
        if kind == "code":
            cell.update(execution_count=None, outputs=[])
        cells.append(cell)
    return {
        "cells": cells,
        "metadata": {"accelerator": "GPU", "kernelspec": {"name": "python3", "display_name": "Python 3"}},
        "nbformat": 4,
        "nbformat_minor": 5,
    }


if __name__ == "__main__":
    out = Path(__file__).with_name("gesture_yolo.ipynb")
    out.write_text(json.dumps(build(), indent=1))
    print("wrote", out)
