"""Generate a standalone notebook with the same prep functions exercised by tests.

Run: python training/build_notebook.py. No datasets are downloaded or trained here.
"""
import hashlib
import inspect
import json
import math
import random
import shutil
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

CLASSES = ["palm", "like", "dislike", "ok", "peace", "no_gesture"]
SPLITS = ("train", "val", "test")
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png"}


@dataclass(frozen=True)
class Sample:
    image: Path
    lines: tuple[str, ...]
    subject: str
    primary: str
    source: str


def normalized_box(values: list, center: bool = False) -> tuple[float, float, float, float]:
    if not isinstance(values, (list, tuple)) or len(values) != 4:
        raise ValueError("Each bounding box must have four coordinates")
    if any(isinstance(v, bool) or not isinstance(v, (float, int)) for v in values):
        raise ValueError("Bounding box coordinates must be numbers")
    x, y, w, h = map(float, values)
    if not all(math.isfinite(v) for v in (x, y, w, h)) or w <= 0 or h <= 0:
        raise ValueError("Bounding boxes must be finite with positive width and height")
    left, top = (x - w / 2, y - h / 2) if center else (x, y)
    if min(left, top) < -1e-6 or left + w > 1 + 1e-6 or top + h > 1 + 1e-6:
        raise ValueError("Bounding box extends outside normalized image bounds")
    return (x, y, w, h) if center else (x + w / 2, y + h / 2, w, h)


def yolo_lines(entry: dict) -> tuple[str, ...]:
    boxes, labels = entry.get("bboxes"), entry.get("labels")
    if not isinstance(boxes, list) or not isinstance(labels, list) or not boxes or len(boxes) != len(labels):
        raise ValueError("Annotation needs equally sized, nonempty bboxes and labels lists")
    lines = []
    for box, label in zip(boxes, labels):
        if label not in CLASSES:
            raise ValueError(f"Unsupported gesture label {label!r}; do not silently drop hand boxes")
        lines.append(f"{CLASSES.index(label)} " + " ".join(f"{v:.8f}" for v in normalized_box(box)))
    return tuple(lines)


def validate_yolo_lines(text: str) -> tuple[str, ...]:
    lines = []
    for line in text.splitlines():
        fields = line.split()
        if len(fields) != 5:
            raise ValueError("Each YOLO label needs class_id center_x center_y width height")
        try:
            class_id = int(fields[0])
            coords = normalized_box([float(v) for v in fields[1:]], center=True)
        except ValueError as exc:
            raise ValueError(f"Invalid YOLO label: {line!r}: {exc}") from exc
        if str(class_id) != fields[0] or not 0 <= class_id < len(CLASSES):
            raise ValueError("YOLO class ID must be an integer from 0 to 5")
        lines.append(f"{class_id} " + " ".join(f"{v:.8f}" for v in coords))
    if not lines:
        raise ValueError("A no_gesture example needs a labeled hand box, not an empty label file")
    return tuple(lines)


def collect_hagrid(root: Path, per_class: int, seed: int) -> list[Sample]:
    annotation_dirs = [p for p in (root / "hagrid_annotations", root / "annotations") if p.is_dir()]
    if len(annotation_dirs) != 1:
        raise ValueError("Provide exactly one hagrid_annotations/ or annotations/ directory")
    samples = []
    for label in CLASSES:
        annotations = {}
        for path in sorted(annotation_dirs[0].rglob(f"{label}.json")):
            entries = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(entries, dict):
                raise ValueError(f"Annotation file must be an image-ID mapping: {path}")
            for image_id, entry in entries.items():
                if image_id in annotations:
                    raise ValueError(f"Duplicate image ID across annotation files: {image_id}")
                annotations[image_id] = entry
        if not annotations:
            raise ValueError(f"Missing annotations for {label}; include HaGRIDv2 standalone no_gesture")
        directories = [p for p in (root / "hagrid_dataset" / label, root / "images" / label, root / label) if p.is_dir()]
        if len(directories) != 1:
            raise ValueError(f"Provide exactly one image directory for {label}")
        images = {}
        for image in sorted(directories[0].rglob("*")):
            if image.suffix.lower() in IMAGE_SUFFIXES:
                if image.stem in images:
                    raise ValueError(f"Ambiguous image ID {image.stem} in {label}")
                images[image.stem] = image
        ids = sorted(annotations)
        random.Random(f"{seed}:{label}").shuffle(ids)
        selected = []
        for image_id in ids:
            if image_id not in images:
                continue
            entry = annotations[image_id]
            if not isinstance(entry, dict) or not isinstance(entry.get("user_id"), str) or not entry["user_id"].strip():
                raise ValueError(f"Missing user_id for {image_id}; splitting requires subject IDs")
            lines = yolo_lines(entry)
            if str(CLASSES.index(label)) not in {line.split()[0] for line in lines}:
                raise ValueError(f"Image {image_id} does not contain its folder gesture {label}")
            selected.append(Sample(images[image_id], lines, "hagrid:" + entry["user_id"], label, "hagrid"))
            if len(selected) == per_class:
                break
        if len(selected) != per_class:
            raise ValueError(f"{label}: need {per_class} annotated images, found {len(selected)}")
        samples.extend(selected)
    return samples


def collect_own_frames(root: Path) -> list[Sample]:
    images = sorted(p for p in root.rglob("*") if p.suffix.lower() in IMAGE_SUFFIXES) if root.is_dir() else []
    if not images:
        return []
    manifest = root / "subjects.json"
    if not manifest.is_file():
        raise ValueError("Team frames require subjects.json mapping relative image paths to subject/session IDs")
    subjects = json.loads(manifest.read_text(encoding="utf-8"))
    if not isinstance(subjects, dict):
        raise ValueError("subjects.json must map relative image paths to subject IDs")
    samples = []
    for image in images:
        relative = image.relative_to(root).as_posix()
        subject = subjects.get(relative)
        if not isinstance(subject, str) or not subject.strip():
            raise ValueError(f"Missing team subject/session ID for {relative}")
        primary = image.relative_to(root).parts[0]
        if primary not in CLASSES:
            raise ValueError(f"Team frame must be under a gesture class directory: {relative}")
        label_file = image.with_suffix(".txt")
        if not label_file.is_file():
            raise ValueError(f"Missing YOLO label file for {relative}")
        lines = validate_yolo_lines(label_file.read_text(encoding="utf-8"))
        if str(CLASSES.index(primary)) not in {line.split()[0] for line in lines}:
            raise ValueError(f"Team frame {relative} does not contain its folder gesture")
        samples.append(Sample(image, lines, "own:" + subject, primary, "own"))
    return samples


def grouped_split(samples: list[Sample], seed: int, ratios: tuple = (0.8, 0.1, 0.1)) -> dict[str, list[Sample]]:
    if len(ratios) != 3 or not all(math.isfinite(v) and v > 0 for v in ratios) or not math.isclose(sum(ratios), 1):
        raise ValueError("Split ratios must be three positive numbers summing to one")
    if not samples:
        raise ValueError("Cannot split an empty dataset")
    groups, seen_hashes = defaultdict(list), {}
    for sample in sorted(samples, key=lambda s: (s.subject, str(s.image))):
        digest = hashlib.sha256(sample.image.read_bytes()).hexdigest()
        if digest in seen_hashes:
            raise ValueError(f"Duplicate image bytes: {sample.image} and {seen_hashes[digest]}")
        seen_hashes[digest] = str(sample.image)
        groups[sample.subject].append(sample)
    if len(groups) < 3:
        raise ValueError("Need at least three distinct subjects/sessions for a held-out split")
    totals = Counter(s.primary for s in samples)
    targets = [{label: totals[label] * ratio for label in CLASSES} for ratio in ratios]
    counts = [Counter(), Counter(), Counter()]
    splits = {name: [] for name in SPLITS}
    ordered = sorted(groups)
    random.Random(seed).shuffle(ordered)
    ordered.sort(key=lambda subject: -len(groups[subject]))
    for subject in ordered:
        batch = groups[subject]
        add = Counter(s.primary for s in batch)
        # Whole subjects stay together, so exact image ratios may be impossible.
        def cost(index: int) -> float:
            return sum(((counts[index][c] + add[c] - targets[index][c]) ** 2
                        - (counts[index][c] - targets[index][c]) ** 2) / max(targets[index][c], 1)
                       for c in CLASSES)
        index = min(range(3), key=cost)
        splits[SPLITS[index]].extend(batch)
        counts[index].update(add)
    for split, items in splits.items():
        present = {int(line.split()[0]) for sample in items for line in sample.lines}
        missing = [CLASSES[i] for i in range(len(CLASSES)) if i not in present]
        if missing:
            raise ValueError(f"{split} lacks {missing}; provide more distinct subjects per class")
    return splits


def prepare_dataset(hagrid_root: Path, own_frames: Path, out: Path, per_class: int = 800,
                    seed: int = 42, ratios: tuple = (0.8, 0.1, 0.1)) -> dict:
    hagrid_root, own_frames, out = hagrid_root.resolve(), own_frames.resolve(), out.resolve()
    for source in (hagrid_root, own_frames):
        if out == source or out in source.parents or source in out.parents:
            raise ValueError("Dataset output must be separate from input directories")
    if out == out.parent:
        raise ValueError("Dataset output cannot be a filesystem root")
    if out.exists() and (not out.is_dir() or any(out.iterdir())):
        raise FileExistsError(f"Refusing existing nonempty dataset output: {out}. Choose a new output directory.")
    if isinstance(per_class, bool) or not isinstance(per_class, int) or per_class < 1:
        raise ValueError("per_class must be a positive integer")
    hagrid, own = collect_hagrid(hagrid_root, per_class, seed), collect_own_frames(own_frames)
    splits = grouped_split(hagrid + own, seed, ratios)
    report = {"seed": seed, "target_ratios": list(ratios), "split_unit": "subject/session",
              "hagrid_images_per_class": dict(Counter(s.primary for s in hagrid)),
              "own_images_per_class": dict(Counter(s.primary for s in own)), "splits": {}}
    manifest = []
    for split, items in splits.items():
        boxes = Counter(CLASSES[int(line.split()[0])] for item in items for line in item.lines)
        report["splits"][split] = {"images": len(items), "actual_ratio": len(items) / (len(hagrid) + len(own)),
                                   "subjects": len({s.subject for s in items}), "boxes": {c: boxes[c] for c in CLASSES}}
        (out / split / "images").mkdir(parents=True, exist_ok=False)
        (out / split / "labels").mkdir(parents=True, exist_ok=False)
        for index, item in enumerate(items):
            stem = f"{split}_{index:06d}"
            shutil.copyfile(item.image, out / split / "images" / (stem + item.image.suffix.lower()))
            (out / split / "labels" / (stem + ".txt")).write_text("\n".join(item.lines) + "\n", encoding="utf-8")
            manifest.append({"split": split, "stem": stem, "source": item.source, "image": str(item.image),
                             "subject": item.subject, "sha256": hashlib.sha256(item.image.read_bytes()).hexdigest()})
        print(split, json.dumps(report["splits"][split], sort_keys=True))
    # JSON is a YAML subset, so preparation needs only the standard library.
    (out / "data.yaml").write_text(json.dumps({"path": str(out), "train": "train/images", "val": "val/images",
                                             "test": "test/images", "names": dict(enumerate(CLASSES))}, indent=2), encoding="utf-8")
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    (out / "prep_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


PREP_OBJECTS = (Sample, normalized_box, yolo_lines, validate_yolo_lines, collect_hagrid,
                collect_own_frames, grouped_split, prepare_dataset)


def prep_source() -> str:
    imports = "import hashlib, json, math, random, shutil\nfrom collections import Counter, defaultdict\nfrom dataclasses import dataclass\nfrom pathlib import Path\n"
    constants = f"CLASSES = {CLASSES!r}\nSPLITS = {SPLITS!r}\n" + 'IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png"}\n'
    return imports + constants + "\n\n" + "\n\n".join(inspect.getsource(obj) for obj in PREP_OBJECTS)


def notebook_cells() -> list[tuple[str, str]]:
    return [
        ("md", """# Hello Campus: gesture detector (YOLO26n)
One model, six classes: `palm`, `like`, `dislike`, `ok`, `peace`, `no_gesture`.
This notebook has not been run on real data. No training, accuracy or latency results are claimed.
Use Colab GPU for training. Supply the real HaGRID subset, venue frames and labels first.

HaGRID describes a **variant of CC BY-SA 4.0**: see its [README](https://github.com/hukenovs/hagrid#license)
and [specific license](https://github.com/hukenovs/hagrid/blob/master/license/en_us.pdf).
Record dataset version, attribution and applicable license in the project README.
Model workflow: [official YOLO26 documentation](https://docs.ultralytics.com/models/yolo26/).
"""),
        ("code", "%pip -q install 'ultralytics>=8.4,<9' onnx onnxruntime"),
        ("md", """## 1. Inputs
Download the six selected classes and annotations from the [HaGRID README](https://github.com/hukenovs/hagrid#downloads).
HaGRIDv2 has a standalone `no_gesture` archive. A negative hand is a boxed sixth class, never an empty label.
```
HAGRID_ROOT/hagrid_dataset/<class>/<image_id>.jpg
HAGRID_ROOT/hagrid_annotations/{train,val,test}/<class>.json
```
Aliases `images/` and `annotations/` also work. Annotations require `bboxes`, `labels`, `user_id`.
Team inputs: `OWN_FRAMES/<class>/*.jpg`, adjacent YOLO `.txt` labels and `OWN_FRAMES/subjects.json`.
The JSON maps paths like `palm/frame01.jpg` to opaque subject/session IDs. Give all frames from one
person/session the same ID. Do not include identifying names.

Splitting targets 80/10/10 by image count while keeping subjects together. Actual ratios and every class count
are printed and saved. Groups may prevent exact ratios. Duplicate image bytes are refused.
Choose a new empty output directory; existing nonempty outputs are never deleted.
"""),
        ("code", """from pathlib import Path
HAGRID_ROOT = Path('/content/hagrid')
OWN_FRAMES = Path('/content/own_frames')
OUT = Path('/content/gesture_ds')
PER_CLASS = 800
SPLIT = (0.8, 0.1, 0.1)
SEED = 42
IMGSZ = 416
EPOCHS = 50
PATIENCE = 10
MIN_OWN_PER_CLASS = 50
"""),
        ("md", "## 2. Validate, sample and split by subject"),
        ("code", prep_source()),
        ("code", """report = prepare_dataset(HAGRID_ROOT, OWN_FRAMES, OUT, PER_CLASS, SEED, SPLIT)
print('Own venue images per class:', report['own_images_per_class'])
print('Save prep_report.json and manifest.json as evidence. Synthetic fixtures do not satisfy real-data acceptance.')
"""),
        ("md", """## 3. Measured comparison
COCO-pretrained weights have a different label vocabulary. Their gesture mAP is **not comparable / not measured**,
not a claimed zero. Compare **one epoch of adaptation** against full fine-tuning.
Both start from the same YOLO26n checkpoint and use the same held-out test subjects.
Only validation data selects checkpoints. Do not tune using test results.
"""),
        ("code", """assert all(report['own_images_per_class'].get(c, 0) >= MIN_OWN_PER_CLASS for c in CLASSES), 'Blocked: collect and label 50 to 100 venue frames per class, from multiple subjects/sessions.'
from ultralytics import YOLO
import ultralytics, torch, platform
print({'ultralytics': ultralytics.__version__, 'torch': torch.__version__, 'python': platform.python_version(), 'device': torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'CPU'})
assert torch.cuda.is_available(), 'Select Colab/Kaggle GPU runtime.'
common = dict(data=str(OUT / 'data.yaml'), imgsz=IMGSZ, seed=SEED, deterministic=True, device=0, project='/content/hello_campus_runs')
baseline = YOLO('yolo26n.pt')
baseline.train(**common, epochs=1, name='adaptation_1epoch', exist_ok=False, plots=False)
model = YOLO('yolo26n.pt')
model.train(**common, epochs=EPOCHS, patience=PATIENCE, name='gesture', exist_ok=False)
base_metrics = baseline.val(data=str(OUT / 'data.yaml'), imgsz=IMGSZ, split='test', device=0, nms=False)
ft_metrics = model.val(data=str(OUT / 'data.yaml'), imgsz=IMGSZ, split='test', device=0, nms=False)
"""),
        ("code", """# Print only measured results. Missing-class metrics remain unavailable.
def row(name, metrics):
    return f'| {name} | {metrics.box.map50:.3f} | {metrics.box.map:.3f} |'
print('| Model | mAP50 | mAP50-95 |\\n|---|---|---|')
print('| COCO pretrained, no adaptation | N/A: incompatible classes | N/A |')
print(row('Adaptation baseline, 1 epoch', base_metrics))
print(row('Fine-tuned', ft_metrics))
print('\\n| Class | Precision | Recall | AP50 |\\n|---|---|---|---|')
present = list(ft_metrics.box.ap_class_index)
for class_id, label in enumerate(CLASSES):
    if class_id not in present:
        print(f'| {label} | N/A | N/A | N/A |')
    else:
        precision, recall, ap50, _ = ft_metrics.box.class_result(present.index(class_id))
        print(f'| {label} | {precision:.3f} | {recall:.3f} | {ap50:.3f} |')
"""),
        ("md", """## 4. Export and CPU timing
Export the NMS-free head matching the runtime detector.
Synthetic-tensor timing below measures only ONNX inference on Colab CPU, excluding image decoding,
preprocessing, postprocessing and WebSocket transfer. Re-measure real frames on the demo laptop.
"""),
        ("code", """onnx_path = model.export(format='onnx', imgsz=IMGSZ, opset=17, simplify=True, dynamic=False, nms=False)
import time, numpy as np, onnxruntime as ort
options = ort.SessionOptions()
options.intra_op_num_threads = 2
options.inter_op_num_threads = 1
session = ort.InferenceSession(str(onnx_path), options, providers=['CPUExecutionProvider'])
x = np.random.default_rng(SEED).random((1, 3, IMGSZ, IMGSZ), dtype=np.float32)
input_name = session.get_inputs()[0].name
for _ in range(5):
    session.run(None, {input_name: x})
times = []
for _ in range(50):
    started = time.perf_counter()
    session.run(None, {input_name: x})
    times.append((time.perf_counter() - started) * 1000)
print(f'Colab CPU inference only: p50 {np.median(times):.1f} ms, p95 {np.percentile(times, 95):.1f} ms')
print('Output shapes:', [output.shape for output in session.get_outputs()])
print('Export:', onnx_path)
"""),
        ("code", """from google.colab import files
files.download(str(onnx_path))  # Save as backend/vision/weights/gesture.onnx.
files.download(str(OUT / 'prep_report.json'))
"""),
    ]


def build() -> dict:
    cells = []
    for index, (kind, source) in enumerate(notebook_cells()):
        cell = {"cell_type": "markdown" if kind == "md" else "code", "id": f"cell-{index:02d}",
                "metadata": {}, "source": source.splitlines(keepends=True)}
        if kind == "code":
            cell.update(execution_count=None, outputs=[])
        cells.append(cell)
    return {"cells": cells, "metadata": {"accelerator": "GPU", "kernelspec": {"name": "python3", "display_name": "Python 3"}},
            "nbformat": 4, "nbformat_minor": 5}


if __name__ == "__main__":
    destination = Path(__file__).with_name("gesture_yolo.ipynb")
    destination.write_text(json.dumps(build(), indent=1) + "\n", encoding="utf-8")
    print("wrote", destination)
