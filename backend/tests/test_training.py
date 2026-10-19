"""Synthetic HaGRID-shaped fixtures only. These tests claim no real training or accuracy."""
import json
import struct
import zlib
from pathlib import Path

import pytest

from training.build_notebook import (
    CLASSES, build, collect_own_frames, prepare_dataset, prep_source,
    validate_yolo_lines, yolo_lines,
)


def synthetic_png(number: int) -> bytes:
    """Unique valid 1x1 PNG fixture, created without any training/image dependencies."""
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">2I5B", 1, 1, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(b"\0" + number.to_bytes(3, "big"))) + chunk(b"IEND", b""))


@pytest.fixture
def synthetic_hagrid(tmp_path):
    root = tmp_path / "synthetic_hagrid"
    annotation_dir = root / "hagrid_annotations" / "train"
    annotation_dir.mkdir(parents=True)
    for class_id, label in enumerate(CLASSES):
        directory = root / "hagrid_dataset" / label
        directory.mkdir(parents=True)
        annotations = {}
        for person in range(10):
            image_id = f"synthetic_{label}_{person}"
            (directory / f"{image_id}.png").write_bytes(synthetic_png(class_id * 10 + person))
            annotations[image_id] = {"bboxes": [[0.1, 0.2, 0.3, 0.4]], "labels": [label],
                                     "user_id": f"synthetic_person_{person}"}
        (annotation_dir / f"{label}.json").write_text(json.dumps(annotations), encoding="utf-8")
    return root


def test_synthetic_prep_all_six_classes_exact_counts_no_subject_or_byte_leak(synthetic_hagrid, tmp_path):
    output = tmp_path / "out"
    report = prepare_dataset(synthetic_hagrid, tmp_path / "no_own_frames", output, per_class=10)
    assert report["target_ratios"] == [0.8, 0.1, 0.1]
    assert {name: result["images"] for name, result in report["splits"].items()} == {"train": 48, "val": 6, "test": 6}
    for name, expected in (("train", 8), ("val", 1), ("test", 1)):
        assert report["splits"][name]["boxes"] == dict.fromkeys(CLASSES, expected)
        for label_file in (output / name / "labels").glob("*.txt"):
            text = label_file.read_text()
            assert text.endswith("\n") and "\\n" not in text
            assert validate_yolo_lines(text)
    manifest = json.loads((output / "manifest.json").read_text())
    by_subject = {}
    hashes = set()
    for item in manifest:
        assert by_subject.setdefault(item["subject"], item["split"]) == item["split"]
        assert item["sha256"] not in hashes
        hashes.add(item["sha256"])
    assert len(hashes) == 60
    assert json.loads((output / "prep_report.json").read_text()) == report
    assert list(json.loads((output / "data.yaml").read_text())["names"].values()) == CLASSES


def test_synthetic_sampling_and_split_are_reproducible(synthetic_hagrid, tmp_path):
    first, second = tmp_path / "first", tmp_path / "second"
    report1 = prepare_dataset(synthetic_hagrid, tmp_path / "no_own", first, per_class=10, seed=71)
    report2 = prepare_dataset(synthetic_hagrid, tmp_path / "no_own", second, per_class=10, seed=71)
    assert report1 == report2
    assert (first / "manifest.json").read_bytes() == (second / "manifest.json").read_bytes()


def test_generated_notebook_runs_the_same_prep_code(synthetic_hagrid, tmp_path):
    scope = {"__name__": "__main__"}
    exec(compile(prep_source(), "notebook-prep", "exec"), scope)
    report = scope["prepare_dataset"](synthetic_hagrid, tmp_path / "none", tmp_path / "notebook_out", per_class=10)
    assert report["splits"]["test"]["images"] == 6
    notebook = build()
    assert json.loads(Path("training/gesture_yolo.ipynb").read_text(encoding="utf-8")) == notebook
    for cell in notebook["cells"]:
        if cell["cell_type"] == "code":
            assert cell["outputs"] == [] and cell["execution_count"] is None
            source = "".join(cell["source"])
            if not source.startswith("%pip"):
                compile(source, cell["id"], "exec")


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
def test_bad_team_labels_fail(text):
    with pytest.raises(ValueError):
        validate_yolo_lines(text)


def test_nonempty_dataset_output_is_never_deleted(synthetic_hagrid, tmp_path):
    output = tmp_path / "existing"
    output.mkdir()
    sentinel = output / "keep.txt"
    sentinel.write_text("valuable data")
    with pytest.raises(FileExistsError, match="Refusing existing nonempty"):
        prepare_dataset(synthetic_hagrid, tmp_path / "none", output, per_class=10)
    assert sentinel.read_text() == "valuable data"


def test_overlapping_output_refused(synthetic_hagrid, tmp_path):
    with pytest.raises(ValueError, match="separate"):
        prepare_dataset(synthetic_hagrid, tmp_path / "none", synthetic_hagrid / "output", per_class=10)


def test_missing_no_gesture_is_a_visible_blocker(synthetic_hagrid, tmp_path):
    (synthetic_hagrid / "hagrid_annotations" / "train" / "no_gesture.json").unlink()
    output = tmp_path / "not_written"
    with pytest.raises(ValueError, match="Missing annotations for no_gesture"):
        prepare_dataset(synthetic_hagrid, tmp_path / "none", output, per_class=10)
    assert not output.exists()


def test_duplicate_image_content_is_refused_before_output(synthetic_hagrid, tmp_path):
    images = list((synthetic_hagrid / "hagrid_dataset").rglob("*.png"))
    images[1].write_bytes(images[0].read_bytes())
    output = tmp_path / "not_written"
    with pytest.raises(ValueError, match="Duplicate image bytes"):
        prepare_dataset(synthetic_hagrid, tmp_path / "none", output, per_class=10)
    assert not output.exists()


def test_missing_subject_metadata_blocks_prep(synthetic_hagrid, tmp_path):
    path = synthetic_hagrid / "hagrid_annotations" / "train" / "palm.json"
    data = json.loads(path.read_text())
    del next(iter(data.values()))["user_id"]
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="Missing user_id"):
        prepare_dataset(synthetic_hagrid, tmp_path / "none", tmp_path / "out", per_class=10)


def test_duplicate_image_id_across_original_splits_fails(synthetic_hagrid, tmp_path):
    annotation_dir = synthetic_hagrid / "hagrid_annotations"
    (annotation_dir / "val").mkdir()
    (annotation_dir / "val" / "palm.json").write_bytes((annotation_dir / "train" / "palm.json").read_bytes())
    with pytest.raises(ValueError, match="Duplicate image ID"):
        prepare_dataset(synthetic_hagrid, tmp_path / "none", tmp_path / "out", per_class=10)


def test_insufficient_subjects_for_a_class_blocks_instead_of_empty_metrics(synthetic_hagrid, tmp_path):
    path = synthetic_hagrid / "hagrid_annotations" / "train" / "no_gesture.json"
    data = json.loads(path.read_text())
    for entry in data.values():
        entry["user_id"] = "same_negative_subject"
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="lacks.*no_gesture"):
        prepare_dataset(synthetic_hagrid, tmp_path / "none", tmp_path / "out", per_class=10)


def test_team_frames_need_valid_labels_and_subject_manifest(tmp_path):
    own = tmp_path / "own"
    image = own / "palm" / "fixture.png"
    image.parent.mkdir(parents=True)
    image.write_bytes(synthetic_png(999))
    with pytest.raises(ValueError, match="subjects.json"):
        collect_own_frames(own)
    (own / "subjects.json").write_text(json.dumps({"palm/fixture.png": "synthetic_session"}))
    with pytest.raises(ValueError, match="Missing YOLO label"):
        collect_own_frames(own)
    image.with_suffix(".txt").write_text("0 .5 .5 .2 .2\n")
    samples = collect_own_frames(own)
    assert len(samples) == 1 and samples[0].subject == "own:synthetic_session"
    assert samples[0].primary == "palm" and samples[0].source == "own"
