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

# ADDENDUM-03: palm buzzes, finger counts answer. no_gesture is a per-hand label in the HF sample.
CLASSES = ["palm", "one", "peace", "three", "four", "no_gesture"]
GESTURE_CLASSES = CLASSES[:-1]  # each has its own annotation file; no_gesture boxes ride along in those images
HF_REPO = "cj-mills/hagrid-sample-120k-384p"
HF_FILE = "hagrid-sample-120k-384p.zip"
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


def collect_hagrid(root: Path, per_class: int, seed: int) -> tuple[list[Sample], dict]:
    """Layout-agnostic: finds <class>.json annotation files and images by stem anywhere under root, because the
    sample zip's folder layout is undocumented. Images containing any hand label outside CLASSES are skipped
    whole (never a silently dropped box), and the skip counts are reported."""
    images: dict[str, Path] = {}
    for image in sorted(root.rglob("*")):
        if image.suffix.lower() in IMAGE_SUFFIXES:
            if image.stem in images:
                raise ValueError(f"Ambiguous image ID {image.stem}")
            images[image.stem] = image
    samples, skipped, used = [], Counter(), set()
    for label in GESTURE_CLASSES:
        annotations = {}
        for path in sorted(root.rglob(f"{label}.json")):
            entries = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(entries, dict):
                raise ValueError(f"Annotation file must be an image-ID mapping: {path}")
            for image_id, entry in entries.items():
                if image_id in annotations:
                    raise ValueError(f"Duplicate image ID across annotation files: {image_id}")
                annotations[image_id] = entry
        if not annotations:
            raise ValueError(f"Missing {label}.json annotations under {root}")
        ids = sorted(annotations)
        random.Random(f"{seed}:{label}").shuffle(ids)
        selected = []
        for image_id in ids:
            if image_id not in images or image_id in used:
                skipped["no_image" if image_id not in images else "duplicate"] += 1
                continue
            entry = annotations[image_id]
            if not isinstance(entry, dict) or not isinstance(entry.get("user_id"), str) or not entry["user_id"].strip():
                raise ValueError(f"Missing user_id for {image_id}; splitting requires subject IDs")
            if any(lab not in CLASSES for lab in entry.get("labels") or []):
                skipped["other_gesture_in_image"] += 1
                continue
            lines = yolo_lines(entry)
            if str(CLASSES.index(label)) not in {line.split()[0] for line in lines}:
                raise ValueError(f"Image {image_id} does not contain its annotation-file gesture {label}")
            selected.append(Sample(images[image_id], lines, "hagrid:" + entry["user_id"], label, "hagrid"))
            used.add(image_id)
            if len(selected) == per_class:
                break
        if len(selected) != per_class:
            raise ValueError(f"{label}: need {per_class} usable annotated images, found {len(selected)}")
        samples.extend(selected)
    return samples, dict(skipped)


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
    targets = [{label: totals[label] * ratio for label in GESTURE_CLASSES} for ratio in ratios]
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
                       for c in GESTURE_CLASSES)
        index = min(range(3), key=cost)
        splits[SPLITS[index]].extend(batch)
        counts[index].update(add)
    for split, items in splits.items():
        present = {int(line.split()[0]) for sample in items for line in sample.lines}
        missing = [CLASSES[i] for i in range(len(CLASSES)) if i not in present]
        if missing:
            raise ValueError(f"{split} lacks {missing}; provide more distinct subjects per class")
    return splits


def prepare_dataset(hagrid_root: Path, out: Path, per_class: int = 800,
                    seed: int = 42, ratios: tuple = (0.8, 0.1, 0.1)) -> dict:
    hagrid_root, out = hagrid_root.resolve(), out.resolve()
    if out == hagrid_root or out in hagrid_root.parents or hagrid_root in out.parents:
        raise ValueError("Dataset output must be separate from the input directory")
    if out == out.parent:
        raise ValueError("Dataset output cannot be a filesystem root")
    if out.exists() and (not out.is_dir() or any(out.iterdir())):
        raise FileExistsError(f"Refusing existing nonempty dataset output: {out}. Choose a new output directory.")
    if isinstance(per_class, bool) or not isinstance(per_class, int) or per_class < 1:
        raise ValueError("per_class must be a positive integer")
    hagrid, skipped = collect_hagrid(hagrid_root, per_class, seed)
    splits = grouped_split(hagrid, seed, ratios)
    report = {"seed": seed, "target_ratios": list(ratios), "split_unit": "subject (HaGRID user_id)",
              "dataset": HF_REPO, "hagrid_images_per_class": dict(Counter(s.primary for s in hagrid)),
              "skipped": skipped, "splits": {}}
    manifest = []
    for split, items in splits.items():
        boxes = Counter(CLASSES[int(line.split()[0])] for item in items for line in item.lines)
        report["splits"][split] = {"images": len(items), "actual_ratio": len(items) / len(hagrid),
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
                grouped_split, prepare_dataset)


def prep_source() -> str:
    imports = "import hashlib, json, math, random, shutil\nfrom collections import Counter, defaultdict\nfrom dataclasses import dataclass\nfrom pathlib import Path\n"
    constants = (f"CLASSES = {CLASSES!r}\nGESTURE_CLASSES = {GESTURE_CLASSES!r}\nHF_REPO = {HF_REPO!r}\n"
                 f"HF_FILE = {HF_FILE!r}\nSPLITS = {SPLITS!r}\n") + 'IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png"}\n'
    return imports + constants + "\n\n" + "\n\n".join(inspect.getsource(obj) for obj in PREP_OBJECTS)


def notebook_cells() -> list[tuple[str, str]]:
    return [
        ("md", """# Hello Campus: Buzzer Quiz gesture detector (YOLO26n)
One model, six classes (ADDENDUM-03): `palm` (buzz), `one`, `peace` (means 2), `three`, `four`, `no_gesture`.
No results are claimed until this notebook has run on Colab GPU. Copy the printed tables into README.

Data: [cj-mills/hagrid-sample-120k-384p](https://huggingface.co/datasets/cj-mills/hagrid-sample-120k-384p),
127,331 HaGRID images at 384p, license **CC BY-SA 4.0**. Original dataset:
[HaGRID](https://github.com/hukenovs/hagrid) by Alexander Kapitanov, Andrey Makhlyarchuk and Karina Kvanchiani.
Record this attribution in the project README. Model workflow:
[YOLO26 docs](https://docs.ultralytics.com/models/yolo26/).
"""),
        ("code", "%pip -q install 'ultralytics>=8.4,<9' onnx onnxruntime huggingface_hub"),
        ("md", """## 1. Download and inspect (about 3.5 GB)
The zip layout is not documented, so the prep code finds `<class>.json` annotation files and images by name
anywhere under `HAGRID_ROOT`. The inspection cell prints what it found; check it before preparing.
"""),
        # Defined here, before first use; the prep cell below repeats them for standalone use (M-007).
        ("code", f"HF_REPO = {HF_REPO!r}\nHF_FILE = {HF_FILE!r}\n" + """import zipfile
from collections import Counter
from pathlib import Path
from huggingface_hub import hf_hub_download
HAGRID_ROOT = Path('/content/hagrid')
if not HAGRID_ROOT.exists():
    archive = hf_hub_download(repo_id=HF_REPO, filename=HF_FILE, repo_type='dataset', local_dir='/content')
    with zipfile.ZipFile(archive) as z:
        z.extractall(HAGRID_ROOT)
print('Top level:', sorted(p.name for p in HAGRID_ROOT.iterdir())[:20])
print('Annotation files:', sorted(p.relative_to(HAGRID_ROOT).as_posix() for p in HAGRID_ROOT.rglob('*.json'))[:40])
print('Images by suffix:', Counter(p.suffix.lower() for p in HAGRID_ROOT.rglob('*') if p.is_file()))
"""),
        ("code", """OUT = Path('/content/gesture_ds')
PER_CLASS = 800
SPLIT = (0.8, 0.1, 0.1)
SEED = 42
IMGSZ = 416
EPOCHS = 40
PATIENCE = 10
"""),
        ("md", """## 2. Validate, sample and split by subject
About 800 images per gesture class, 80/10/10, whole HaGRID `user_id` subjects kept in one split.
`no_gesture` boxes come from the second hand in those images. Images with any other gesture label are skipped
whole and counted in `skipped`. Every split must contain all six classes or prep stops.
"""),
        ("code", prep_source()),
        ("code", """report = prepare_dataset(HAGRID_ROOT, OUT, PER_CLASS, SEED, SPLIT)
print('Skipped:', report['skipped'])
print('| Split | Images | Subjects | ' + ' | '.join(CLASSES) + ' |')
for name, r in report['splits'].items():
    print(f"| {name} | {r['images']} | {r['subjects']} | " + ' | '.join(str(r['boxes'][c]) for c in CLASSES) + ' |')
"""),
        ("md", """## 3. Train and compare
COCO-pretrained weights have no gesture classes, so their gesture mAP is **not measured**, not zero.
The baseline is one epoch of adaptation; both runs start from `yolo26n.pt` and use the same held-out subjects.
Only validation data selects checkpoints.
"""),
        ("code", """from ultralytics import YOLO
import ultralytics, torch, platform
print({'ultralytics': ultralytics.__version__, 'torch': torch.__version__, 'python': platform.python_version(),
       'device': torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'CPU'})
assert torch.cuda.is_available(), 'Select a GPU runtime: Runtime > Change runtime type.'
common = dict(data=str(OUT / 'data.yaml'), imgsz=IMGSZ, seed=SEED, deterministic=True, device=0,
              project='/content/hello_campus_runs')
baseline = YOLO('yolo26n.pt')
baseline.train(**common, epochs=1, name='adaptation_1epoch', exist_ok=False, plots=False)
model = YOLO('yolo26n.pt')
model.train(**common, epochs=EPOCHS, patience=PATIENCE, name='gesture', exist_ok=False)
base_metrics = baseline.val(data=str(OUT / 'data.yaml'), imgsz=IMGSZ, split='test', device=0)
ft_metrics = model.val(data=str(OUT / 'data.yaml'), imgsz=IMGSZ, split='test', device=0)
"""),
        ("code", """def row(name, metrics):
    return f'| {name} | {metrics.box.map50:.3f} | {metrics.box.map:.3f} |'
print('| Model | mAP50 | mAP50-95 |\\n|---|---|---|')
print('| COCO pretrained, no adaptation | not measured: no gesture classes | not measured |')
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
YOLO26 exports an NMS-free end-to-end head by default. `end2end=False` keeps the classic
`[1, 4 + classes, N]` output the backend decoder parses; the shape check below confirms it.
Timing covers ONNX inference only on Colab CPU. Re-measure real frames on the demo laptop.
"""),
        ("code", """onnx_path = model.export(format='onnx', imgsz=IMGSZ, opset=17, simplify=True, dynamic=False, end2end=False)
import time, numpy as np, onnxruntime as ort
options = ort.SessionOptions()
options.intra_op_num_threads = 2
options.inter_op_num_threads = 1
session = ort.InferenceSession(str(onnx_path), options, providers=['CPUExecutionProvider'])
shapes = [o.shape for o in session.get_outputs()]
print('Output shapes:', shapes)
assert len(shapes) == 1 and shapes[0][1] == 4 + len(CLASSES), 'Unexpected head: check end2end=False took effect'
print('Embedded class names:', session.get_modelmeta().custom_metadata_map.get('names'))
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
"""),
        ("code", """# Save as backend/vision/weights/gesture.onnx (gitignored). Keep a USB copy.
# files.download needs the Colab web UI, so the outputs are also copied to Google Drive when it can be mounted.
import shutil
outputs = [Path(onnx_path), OUT / 'prep_report.json']
try:
    from google.colab import drive
    drive.mount('/content/drive')
    target = Path('/content/drive/MyDrive/hello_campus')
    target.mkdir(parents=True, exist_ok=True)
    for f in outputs:
        shutil.copy(f, target / f.name)
    print('Copied to Google Drive:', target)
except Exception as exc:  # noqa: BLE001, Drive is a convenience
    print('Drive copy skipped:', exc)
try:
    from google.colab import files
    for f in outputs:
        files.download(str(f))
except Exception as exc:  # noqa: BLE001, e.g. running through an editor extension
    print('Browser download unavailable:', exc)
for f in outputs:
    print('Output file:', f.resolve())
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
