"""Behavioral tests for the deterministic router dataset builder."""

from __future__ import annotations

import json
from pathlib import Path

from backend.router.dataset_builder import build_router_dataset
from backend.router.labels import SIGNALS, V1_DOMAINS


def _read_jsonl(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _write_fixture_repo(root: Path) -> None:
    benchmark = root / "tests" / "benchmark"
    benchmark.mkdir(parents=True)
    (benchmark / "regression_cases.json").write_text(
        json.dumps(
            [
                {
                    "question": "تعداد دانش آموزان فعال تهران",
                    "label": "student",
                    "expected": {"group": "student"},
                },
                {
                    "question": "تعداد دانش‌آموزان فعال تهران",
                    "label": "employee",
                    "expected": {"group": "employee"},
                },
                {
                    "question": "حقوق کارمند با کد ملی 1234567890",
                    "expected": {"group": "salary"},
                },
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    feedback = root / "feedback"
    feedback.mkdir()
    (feedback / "feedback.json").write_text(
        json.dumps(
            [
                {"text": "اطلاعات مدارس تهران", "reviewed": True},
                {"text": "اطلاعات محرمانه کارمند", "reviewed": False},
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    semantic = root / "schema" / "tenants" / "demo"
    semantic.mkdir(parents=True)
    (semantic / "semantic_active.json").write_text(
        json.dumps(
            {
                "tables": [
                    {"name": "retirement_records", "entity": "retirement", "aliases": ["بازنشستگی"]}
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def test_builder_writes_contract_and_reviewed_subset(tmp_path: Path) -> None:
    _write_fixture_repo(tmp_path)
    result = build_router_dataset(tmp_path)
    raw = _read_jsonl(result.raw_path)
    reviewed = _read_jsonl(result.reviewed_path)

    assert raw
    assert reviewed
    assert len(reviewed) <= len(raw)
    assert all(set(item) == {"text", "label", "family_id", "source", "reviewed", "signals"} for item in raw)
    assert all(item["label"] in V1_DOMAINS for item in raw)
    assert all(item["label"] not in SIGNALS for item in raw)
    assert all(item["reviewed"] is True for item in reviewed)


def test_builder_is_deterministic_and_deduplicates_normalized_text(tmp_path: Path) -> None:
    _write_fixture_repo(tmp_path)
    first = build_router_dataset(tmp_path)
    first_bytes = tuple(path.read_bytes() for path in (first.raw_path, first.reviewed_path, first.families_path))
    second = build_router_dataset(tmp_path)
    second_bytes = tuple(path.read_bytes() for path in (second.raw_path, second.reviewed_path, second.families_path))

    assert first_bytes == second_bytes
    examples = _read_jsonl(first.raw_path)
    student_questions = [item for item in examples if "دانش آموزان فعال تهران" in str(item["text"])]
    assert len(student_questions) == 1


def test_builder_redacts_national_ids_and_records_conflicts(tmp_path: Path) -> None:
    _write_fixture_repo(tmp_path)
    result = build_router_dataset(tmp_path)
    raw_text = result.raw_path.read_text(encoding="utf-8")
    manifest = json.loads(result.families_path.read_text(encoding="utf-8"))

    assert "1234567890" not in raw_text
    assert "<NATIONAL_ID>" in raw_text
    assert manifest["counts"]["conflicts"] == 1
    assert manifest["conflicts"][0]["labels"] == ["employee", "student"]


def test_unreviewed_feedback_is_not_collected(tmp_path: Path) -> None:
    _write_fixture_repo(tmp_path)
    result = build_router_dataset(tmp_path)
    texts = {item["text"] for item in _read_jsonl(result.raw_path)}
    assert "اطلاعات محرمانه کارمند" not in texts
    assert "اطلاعات مدارس تهران" in texts


def test_missing_optional_sources_produces_empty_valid_outputs(tmp_path: Path) -> None:
    output = tmp_path / "custom-output"
    result = build_router_dataset(tmp_path, output)
    manifest = json.loads(result.families_path.read_text(encoding="utf-8"))

    assert result.raw_count == 0
    assert result.reviewed_count == 0
    assert result.raw_path.read_text(encoding="utf-8") == ""
    assert manifest["labels"] == sorted(V1_DOMAINS)


def test_repository_build_contains_multiple_useful_domains(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    result = build_router_dataset(repo_root, tmp_path / "repository-build")
    examples = _read_jsonl(result.raw_path)
    labels = {item["label"] for item in examples}

    assert result.raw_count > 20
    assert result.reviewed_count > 10
    assert {"student", "employee", "school", "salary", "organization", "retirement"} <= labels
