"""Synthetic HaGRID-sample-shaped fixtures only (ADDENDUM-03 T4.0 prep). No real training or accuracy is claimed."""
import json
import struct
import zlib
from pathlib import Path

import pytest

from training.build_notebook import (
    CLASSES, GESTURE_CLASSES, HF_FILE, HF_REPO, build, prepare_dataset, prep_source, validate_yolo_lines,
    yolo_lines,
)


def synthetic_png(number: int) -> bytes:
    """Unique valid 1x1 PNG fixture, created without any training/image dependencies."""
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">2I5B", 1, 1, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(b"\0" + number.to_bytes(3, "big"))) + chunk(b"IEND", b""))


@pytest.fixture
def synthetic_hagrid(tmp_path):
    """Mimics the HF sample: per-gesture annotation JSON, no_gesture as a second-hand label, arbitrary folders."""
    root = tmp_path / "synthetic_hagrid"
    annotation_dir = root / "some_layout" / "ann_train_val"
    annotation_dir.mkdir(parents=True)
    for class_id, label in enumerate(GESTURE_CLASSES):
        directory = root / "some_layout" / "images" / f"train_val_{label}"
        directory.mkdir(parents=True)
        annotations = {}
        for person in range(10):
            image_id = f"synthetic_{label}_{person}"
            (directory / f"{image_id}.png").write_bytes(synthetic_png(class_id * 10 + person))
            annotations[image_id] = {"bboxes": [[0.1, 0.2, 0.3, 0.4], [0.6, 0.5, 0.2, 0.3]],
                                     "labels": [label, "no_gesture"], "user_id": f"synthetic_person_{person}"}
        (annotation_dir / f"{label}.json").write_text(json.dumps(annotations), encoding="utf-8")
    return root


def test_classes_match_addendum_03():
    assert CLASSES == ["palm", "one", "peace", "three", "four", "no_gesture"]
    assert HF_REPO == "cj-mills/hagrid-sample-120k-384p" and HF_FILE.endswith(".zip")


def test_prep_all_six_classes_exact_counts_no_subject_or_byte_leak(synthetic_hagrid, tmp_path):
    output = tmp_path / "out"
    report = prepare_dataset(synthetic_hagrid, output, per_class=10)
    assert report["target_ratios"] == [0.8, 0.1, 0.1] and report["skipped"] == {}
    assert {name: result["images"] for name, result in report["splits"].items()} == {"train": 40, "val": 5, "test": 5}
    for name, expected in (("train", 8), ("val", 1), ("test", 1)):
        boxes = report["splits"][name]["boxes"]
        assert {c: boxes[c] for c in GESTURE_CLASSES} == dict.fromkeys(GESTURE_CLASSES, expected)
        assert boxes["no_gesture"] == expected * len(GESTURE_CLASSES)
        for label_file in (output / name / "labels").glob("*.txt"):
            assert validate_yolo_lines(label_file.read_text())
    manifest = json.loads((output / "manifest.json").read_text())
    by_subject, hashes = {}, set()
    for item in manifest:
        assert by_subject.setdefault(item["subject"], item["split"]) == item["split"]
        assert item["sha256"] not in hashes
        hashes.add(item["sha256"])
    assert len(hashes) == 50
    assert list(json.loads((output / "data.yaml").read_text())["names"].values()) == CLASSES


def test_images_with_other_gestures_are_skipped_whole(synthetic_hagrid, tmp_path):
    path = synthetic_hagrid / "some_layout" / "ann_train_val" / "palm.json"
    data = json.loads(path.read_text())
    extra = synthetic_hagrid / "some_layout" / "images" / "train_val_palm" / "synthetic_palm_extra.png"
    extra.write_bytes(synthetic_png(999))
    data["synthetic_palm_extra"] = {"bboxes": [[0.1, 0.1, 0.2, 0.2], [0.5, 0.5, 0.2, 0.2]],
                                    "labels": ["palm", "fist"], "user_id": "synthetic_person_0"}
    path.write_text(json.dumps(data))
    report = prepare_dataset(synthetic_hagrid, tmp_path / "out", per_class=10)
    assert report["skipped"] == {"other_gesture_in_image": 1}
    assert report["hagrid_images_per_class"]["palm"] == 10


def test_sampling_and_split_are_reproducible(synthetic_hagrid, tmp_path):
    report1 = prepare_dataset(synthetic_hagrid, tmp_path / "first", per_class=10, seed=71)
    report2 = prepare_dataset(synthetic_hagrid, tmp_path / "second", per_class=10, seed=71)
    assert report1 == report2
    assert (tmp_path / "first" / "manifest.json").read_bytes() == (tmp_path / "second" / "manifest.json").read_bytes()


def test_generated_notebook_runs_the_same_prep_code(synthetic_hagrid, tmp_path):
    scope = {"__name__": "__main__"}
    exec(compile(prep_source(), "notebook-prep", "exec"), scope)
    report = scope["prepare_dataset"](synthetic_hagrid, tmp_path / "notebook_out", per_class=10)
    assert report["splits"]["test"]["images"] == 5
    notebook = build()
    assert json.loads(Path("training/gesture_yolo.ipynb").read_text(encoding="utf-8")) == notebook
    sources = "".join("".join(c["source"]) for c in notebook["cells"])
    assert "end2end=False" in sources and "own_frames" not in sources
    for cell in notebook["cells"]:
        if cell["cell_type"] == "code":
            assert cell["outputs"] == [] and cell["execution_count"] is None
            source = "".join(cell["source"])
            if not source.startswith("%pip"):
                compile(source, cell["id"], "exec")


def test_notebook_defines_every_name_before_use():
    """M-007: run the cells in order with Colab-only calls stubbed, so a NameError cannot reach Colab."""
    import ast
    import builtins
    defined = set(dir(builtins)) | {"__name__"}
    for cell in build()["cells"]:
        if cell["cell_type"] != "code":
            continue
        source = "".join(cell["source"])
        if source.startswith("%pip"):
            continue
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                defined.update((a.asname or a.name).split(".")[0] for a in node.names)
            elif isinstance(node, (ast.FunctionDef, ast.ClassDef)):
                defined.add(node.name)
                defined.update(a.arg for a in node.args.args) if isinstance(node, ast.FunctionDef) else None
            elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
                defined.add(node.id)
            elif isinstance(node, (ast.comprehension, ast.ExceptHandler)):
                target = node.target if isinstance(node, ast.comprehension) else None
                for n in ast.walk(target) if target is not None else []:
                    if isinstance(n, ast.Name):
                        defined.add(n.id)
                if isinstance(node, ast.ExceptHandler) and node.name:
                    defined.add(node.name)
        for node in ast.walk(tree):
            if isinstance(node, ast.arg):
                defined.add(node.arg)
        used = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)}
        assert used <= defined, f"{cell['id']} uses names defined later: {sorted(used - defined)}"


def test_no_gesture_is_a_boxed_class_and_xywh_is_converted():
    lines = yolo_lines({"bboxes": [[0.1, 0.2, 0.4, 0.6]], "labels": ["no_gesture"]})
    assert lines == ("5 0.30000000 0.50000000 0.40000000 0.60000000",)


@pytest.mark.parametrize("entry", [
    {"bboxes": [], "labels": []},
    {"bboxes": [[0, 0, 1, 1]], "labels": []},
    {"bboxes": [[0.9, 0, 0.5, 1]], "labels": ["palm"]},
    {"bboxes": [[float("nan"), 0, 0.5, 1]], "labels": ["palm"]},
    {"bboxes": [[0, 0, 0, 1]], "labels": ["palm"]},
    {"bboxes": [[0, 0, True, 1]], "labels": ["palm"]},
    {"bboxes": [[0, 0, 1, 1]], "labels": ["unknown_gesture"]},
])
def test_bad_hagrid_annotations_fail(entry):
    with pytest.raises(ValueError):
        yolo_lines(entry)


@pytest.mark.parametrize("text", ["", "6 .5 .5 .2 .2", "-1 .5 .5 .2 .2", "1.0 .5 .5 .2 .2",
                                  "0 0 0 1 1", "0 nan .5 .2 .2", "0 .5 .5 0 .2", "0 .5 .5"])
def test_bad_yolo_labels_fail(text):
    with pytest.raises(ValueError):
        validate_yolo_lines(text)


def test_nonempty_dataset_output_is_never_deleted(synthetic_hagrid, tmp_path):
    output = tmp_path / "existing"
    output.mkdir()
    sentinel = output / "keep.txt"
    sentinel.write_text("valuable data")
    with pytest.raises(FileExistsError, match="Refusing existing nonempty"):
        prepare_dataset(synthetic_hagrid, output, per_class=10)
    assert sentinel.read_text() == "valuable data"


def test_overlapping_output_refused(synthetic_hagrid):
    with pytest.raises(ValueError, match="separate"):
        prepare_dataset(synthetic_hagrid, synthetic_hagrid / "output", per_class=10)


def test_missing_class_annotations_is_a_visible_blocker(synthetic_hagrid, tmp_path):
    (synthetic_hagrid / "some_layout" / "ann_train_val" / "four.json").unlink()
    output = tmp_path / "not_written"
    with pytest.raises(ValueError, match="Missing four.json"):
        prepare_dataset(synthetic_hagrid, output, per_class=10)
    assert not output.exists()


def test_duplicate_image_content_is_refused_before_output(synthetic_hagrid, tmp_path):
    images = list(synthetic_hagrid.rglob("*.png"))
    images[1].write_bytes(images[0].read_bytes())
    output = tmp_path / "not_written"
    with pytest.raises(ValueError, match="Duplicate image bytes"):
        prepare_dataset(synthetic_hagrid, output, per_class=10)
    assert not output.exists()


def test_missing_subject_metadata_blocks_prep(synthetic_hagrid, tmp_path):
    path = synthetic_hagrid / "some_layout" / "ann_train_val" / "palm.json"
    data = json.loads(path.read_text())
    del next(iter(data.values()))["user_id"]
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="Missing user_id"):
        prepare_dataset(synthetic_hagrid, tmp_path / "out", per_class=10)


def test_duplicate_image_id_across_annotation_files_fails(synthetic_hagrid, tmp_path):
    ann = synthetic_hagrid / "some_layout" / "ann_test"
    ann.mkdir()
    (ann / "palm.json").write_bytes((synthetic_hagrid / "some_layout" / "ann_train_val" / "palm.json").read_bytes())
    with pytest.raises(ValueError, match="Duplicate image ID"):
        prepare_dataset(synthetic_hagrid, tmp_path / "out", per_class=10)


def test_split_missing_a_class_blocks_instead_of_empty_metrics(synthetic_hagrid, tmp_path):
    for label in GESTURE_CLASSES:
        path = synthetic_hagrid / "some_layout" / "ann_train_val" / f"{label}.json"
        data = json.loads(path.read_text())
        for entry in data.values():  # drop the second hand everywhere, so no split has no_gesture
            entry["bboxes"], entry["labels"] = entry["bboxes"][:1], entry["labels"][:1]
        path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="lacks.*no_gesture"):
        prepare_dataset(synthetic_hagrid, tmp_path / "out", per_class=10)
