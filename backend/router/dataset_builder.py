"""Deterministic dataset builder for the Persian intent router."""

from __future__ import annotations

import ast
import json
import re
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable, Iterator

from backend.router.labels import SIGNALS, V1_DOMAINS


DATASET_SCHEMA_VERSION = "router-dataset-v1"
PERSIAN_RE = re.compile(r"[\u0600-\u06ff]")
NATIONAL_ID_RE = re.compile(r"(?<!\d)[۰-۹٠-٩0-9]{10}(?!\d)")
WHITESPACE_RE = re.compile(r"\s+")
SQL_RE = re.compile(r"\b(select|insert|update|delete|drop|alter|create)\b", re.I)
SECRET_RE = re.compile(r"(password|passwd|api[_-]?key|secret|token)\s*[:=]", re.I)

QUESTION_HINTS = frozenset(
    {
        "تعداد",
        "اطلاعات",
        "نشان بده",
        "بگو",
        "کدام",
        "میانگین",
        "کمترین",
        "بیشترین",
        "نام",
        "اسم",
        "شماره",
        "حقوق",
        "مدرسه",
        "دانش آموز",
        "دانش‌آموز",
        "کارمند",
        "بازنشستگی",
        "سازمانی",
    }
)

DOMAIN_TERMS: dict[str, tuple[str, ...]] = {
    "retirement": ("بازنشست", "سنوات", "مستمری", "سابقه خدمت"),
    "salary": ("حقوق", "دستمزد", "مزایا", "کسورات", "خالص پرداخت", "پایه حقوق"),
    "school": ("مدرسه", "مدارس", "دبستان", "دبیرستان", "هنرستان"),
    "student": ("دانش آموز", "دانش‌آموز", "دانش اموز", "دانش‌آموزان", "دانش آموزان"),
    "employee": ("کارمند", "کارکنان", "پرسنل", "معلم", "دبیر"),
    "organization": ("واحد سازمانی", "ساختار سازمان", "اداره کل", "منطقه آموزشی"),
}

ENTITY_TO_DOMAIN = {
    "student": "student",
    "students": "student",
    "employee": "employee",
    "employees": "employee",
    "school": "school",
    "schools": "school",
    "salary": "salary",
    "salary_item": "salary",
    "salary_items": "salary",
    "organization": "organization",
    "organization_unit": "organization",
    "organization_units": "organization",
    "retirement": "retirement",
    "retirement_record": "retirement",
    "retirement_records": "retirement",
}

SOURCE_PRIORITY = {
    "regression_test": 50,
    "benchmark": 45,
    "manual_test": 40,
    "semantic_metadata": 35,
    "reviewed_feedback": 30,
    "safety_test": 25,
    "python_test": 20,
}


@dataclass(frozen=True)
class DatasetExample:
    """A single domain-routing training example."""

    text: str
    label: str
    family_id: str
    source: str
    reviewed: bool
    signals: tuple[str, ...] = ()

    def to_json(self) -> dict[str, object]:
        """Return a stable JSON-compatible representation."""
        payload = asdict(self)
        payload["signals"] = list(self.signals)
        return payload


@dataclass(frozen=True)
class BuildResult:
    """Paths and counts produced by a dataset build."""

    raw_path: Path
    reviewed_path: Path
    families_path: Path
    raw_count: int
    reviewed_count: int


def normalize_persian(text: str) -> str:
    """Normalize Arabic variants, spacing, and sensitive identifiers."""
    normalized = str(text).translate(str.maketrans({"ي": "ی", "ى": "ی", "ك": "ک", "ۀ": "ه"}))
    normalized = normalized.replace("\u200c", " ")
    normalized = NATIONAL_ID_RE.sub("<NATIONAL_ID>", normalized)
    return WHITESPACE_RE.sub(" ", normalized).strip(" \t\r\n\"'،,.;؛")


def _dedupe_key(text: str) -> str:
    return normalize_persian(text).casefold()


def _is_question_text(text: str) -> bool:
    if not 4 <= len(text) <= 500 or not PERSIAN_RE.search(text):
        return False
    if SQL_RE.search(text) or SECRET_RE.search(text):
        return False
    return any(hint in text for hint in QUESTION_HINTS) or text.endswith("؟")


def infer_domain(text: str, metadata: dict[str, Any] | None = None) -> str:
    """Infer one conservative V1 domain from text and explicit metadata."""
    normalized = normalize_persian(text)
    metadata = metadata or {}
    explicit_candidates = (
        metadata.get("label"),
        metadata.get("domain"),
        metadata.get("entity"),
        metadata.get("table"),
    )
    for candidate in explicit_candidates:
        if not isinstance(candidate, str):
            continue
        canonical = ENTITY_TO_DOMAIN.get(candidate.casefold(), candidate.casefold())
        if canonical in V1_DOMAINS:
            return canonical

    for domain, terms in DOMAIN_TERMS.items():
        if any(term in normalized for term in terms):
            return domain

    for candidate in (metadata.get("group"),):
        if not isinstance(candidate, str):
            continue
        canonical = ENTITY_TO_DOMAIN.get(candidate.casefold(), candidate.casefold())
        if canonical in V1_DOMAINS:
            return canonical
    return "generic_semantic"


def infer_signals(text: str, metadata: dict[str, Any] | None = None) -> tuple[str, ...]:
    """Return orthogonal router signals without changing the domain label."""
    normalized = normalize_persian(text)
    found: set[str] = set()
    if any(word in normalized for word in ("حذف کن", "پاک کن", "به روز کن", "تغییر بده")):
        found.add("unsafe")
    if any(word in normalized for word in ("کمترین", "بیشترین", "رتبه", "برتر")):
        found.add("ranking")
    if " و " in normalized and sum(any(term in normalized for term in terms) for terms in DOMAIN_TERMS.values()) > 1:
        found.add("multi_intent")
    metadata = metadata or {}
    explicit = metadata.get("signals", ())
    if isinstance(explicit, str):
        explicit = (explicit,)
    if isinstance(explicit, (list, tuple, set)):
        found.update(str(item) for item in explicit if str(item) in SIGNALS)
    return tuple(sorted(found))


def infer_family(text: str, label: str, signals: Iterable[str] = ()) -> str:
    """Create a stable intent-family identifier."""
    normalized = normalize_persian(text)
    signal_set = set(signals)
    if "unsafe" in signal_set:
        intent = "unsafe"
    elif "ranking" in signal_set:
        intent = "ranking"
    elif any(word in normalized for word in ("تعداد", "چند")):
        intent = "count"
    elif any(word in normalized for word in ("میانگین", "مجموع", "جمع ")):
        intent = "aggregate"
    elif any(word in normalized for word in ("اطلاعات", "تمام ستون", "مشخصات")):
        intent = "profile"
    elif any(word in normalized for word in ("نام ", "اسم ", "شماره ", "کد ملی")):
        intent = "lookup"
    else:
        intent = "query"

    qualifiers: list[str] = []
    if any(word in normalized for word in ("استان", "شهر", "منطقه")):
        qualifiers.append("location")
    if "وضعیت" in normalized or "فعال" in normalized:
        qualifiers.append("status")
    if "کد ملی" in normalized:
        qualifiers.append("identity")
    return "_".join((label, intent, *qualifiers))


def _source_category(path: Path, payload: dict[str, Any] | None = None) -> str:
    name = path.name.casefold()
    if "regression" in name:
        return "regression_test"
    if "benchmark" in path.as_posix().casefold() or "cases" in name:
        return "benchmark"
    if "feedback" in name:
        return "reviewed_feedback"
    if "safety" in name:
        return "safety_test"
    if payload and payload.get("reviewed") is True:
        return "manual_test"
    return "manual_test"


def _walk_json(value: Any) -> Iterator[dict[str, Any]]:
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk_json(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_json(child)


def _text_from_mapping(item: dict[str, Any]) -> str | None:
    for key in ("question", "query", "text", "user_question", "prompt"):
        value = item.get(key)
        if isinstance(value, str):
            return value
    return None


def _metadata_for(item: dict[str, Any]) -> dict[str, Any]:
    expected = item.get("expected")
    merged = dict(item)
    if isinstance(expected, dict):
        for key, value in expected.items():
            merged.setdefault(key, value)
    return merged


def _json_examples(path: Path, repo_root: Path) -> Iterator[DatasetExample]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return
    relative = path.relative_to(repo_root).as_posix()
    for item in _walk_json(payload):
        text_value = _text_from_mapping(item)
        if text_value is None:
            continue
        text = normalize_persian(text_value)
        if not _is_question_text(text):
            continue
        metadata = _metadata_for(item)
        category = _source_category(path, metadata)
        is_feedback = "feedback" in path.name.casefold()
        if is_feedback and metadata.get("reviewed") is not True:
            continue
        reviewed = category in {"regression_test", "benchmark", "safety_test"} or metadata.get("reviewed") is True
        label = infer_domain(text, metadata)
        signals = infer_signals(text, metadata)
        yield DatasetExample(
            text=text,
            label=label,
            family_id=infer_family(text, label, signals),
            source=f"{category}:{relative}",
            reviewed=reviewed,
            signals=signals,
        )


def _python_test_examples(path: Path, repo_root: Path) -> Iterator[DatasetExample]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, SyntaxError):
        return
    relative = path.relative_to(repo_root).as_posix()
    category = "safety_test" if "safety" in path.name.casefold() else "python_test"
    for node in ast.walk(tree):
        if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
            continue
        text = normalize_persian(node.value)
        if not _is_question_text(text):
            continue
        label = infer_domain(text)
        signals = infer_signals(text)
        yield DatasetExample(
            text=text,
            label=label,
            family_id=infer_family(text, label, signals),
            source=f"{category}:{relative}",
            reviewed=category == "safety_test",
            signals=signals,
        )


def _semantic_examples(path: Path, repo_root: Path) -> Iterator[DatasetExample]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return
    relative = path.relative_to(repo_root).as_posix()
    tables = payload.get("tables", []) if isinstance(payload, dict) else []
    if not isinstance(tables, list):
        return
    for table in tables:
        if not isinstance(table, dict):
            continue
        metadata = {"entity": table.get("entity"), "table": table.get("name")}
        label = infer_domain("", metadata)
        aliases = table.get("aliases", [])
        if not isinstance(aliases, list):
            continue
        for alias in aliases:
            if not isinstance(alias, str) or not PERSIAN_RE.search(alias):
                continue
            text = normalize_persian(f"اطلاعات {alias} را نشان بده")
            signals = infer_signals(text, metadata)
            yield DatasetExample(
                text=text,
                label=label,
                family_id=infer_family(text, label, signals),
                source=f"semantic_metadata:{relative}",
                reviewed=True,
                signals=signals,
            )


def collect_examples(repo_root: Path) -> list[DatasetExample]:
    """Collect candidate examples from supported repository sources."""
    examples: list[DatasetExample] = []
    tests_dir = repo_root / "tests"
    if tests_dir.exists():
        json_paths = sorted(
            path
            for path in tests_dir.rglob("*.json")
            if "results" not in {part.casefold() for part in path.parts}
        )
        for path in json_paths:
            examples.extend(_json_examples(path, repo_root))
        for path in sorted(tests_dir.glob("test_*safety*.py")):
            examples.extend(_python_test_examples(path, repo_root))

    feedback_candidates: list[Path] = []
    feedback_root = repo_root / "feedback"
    if feedback_root.exists():
        feedback_candidates.extend(feedback_root.glob("**/*"))
    tenant_root = repo_root / "schema" / "tenants"
    if tenant_root.exists():
        feedback_candidates.extend(tenant_root.glob("*/feedback.json"))
    feedback_candidates = sorted(set(feedback_candidates))
    for path in feedback_candidates:
        if path.is_file() and path.suffix.casefold() in {".json", ".jsonl"}:
            if path.suffix.casefold() == ".jsonl":
                for line_number, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
                    try:
                        item = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if isinstance(item, dict) and item.get("reviewed") is True:
                        text = _text_from_mapping(item)
                        if text and _is_question_text(normalize_persian(text)):
                            clean = normalize_persian(text)
                            label = infer_domain(clean, item)
                            signals = infer_signals(clean, item)
                            examples.append(DatasetExample(clean, label, infer_family(clean, label, signals), f"reviewed_feedback:{path.relative_to(repo_root).as_posix()}#{line_number}", True, signals))
                continue
            examples.extend(_json_examples(path, repo_root))

    semantic_paths = sorted((repo_root / "schema" / "tenants").glob("*/semantic_active.json"))
    for path in semantic_paths:
        examples.extend(_semantic_examples(path, repo_root))
    return examples


def _resolve_examples(examples: Iterable[DatasetExample]) -> tuple[list[DatasetExample], list[dict[str, object]]]:
    grouped: dict[str, list[DatasetExample]] = {}
    for example in examples:
        if example.label not in V1_DOMAINS:
            continue
        grouped.setdefault(_dedupe_key(example.text), []).append(example)

    selected: list[DatasetExample] = []
    conflicts: list[dict[str, object]] = []
    for key in sorted(grouped):
        candidates = grouped[key]
        labels = sorted({candidate.label for candidate in candidates})
        ranked = sorted(
            candidates,
            key=lambda candidate: (
                not candidate.reviewed,
                -SOURCE_PRIORITY.get(candidate.source.split(":", 1)[0], 0),
                candidate.label,
                candidate.source,
            ),
        )
        winner = ranked[0]
        selected.append(winner)
        if len(labels) > 1:
            conflicts.append(
                {
                    "text": winner.text,
                    "labels": labels,
                    "selected_label": winner.label,
                    "selected_source": winner.source,
                }
            )
    return sorted(selected, key=lambda item: (_dedupe_key(item.text), item.label)), conflicts


def _write_jsonl(path: Path, examples: Iterable[DatasetExample]) -> None:
    lines = [json.dumps(example.to_json(), ensure_ascii=False, sort_keys=True) for example in examples]
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


def build_router_dataset(repo_root: Path, output_dir: Path | None = None) -> BuildResult:
    """Build raw/reviewed datasets and their deterministic manifest."""
    repo_root = repo_root.resolve()
    output_dir = (output_dir or repo_root / "training" / "router").resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    collected = collect_examples(repo_root)
    raw, conflicts = _resolve_examples(collected)
    reviewed = [example for example in raw if example.reviewed]

    raw_path = output_dir / "dataset_raw.jsonl"
    reviewed_path = output_dir / "dataset_reviewed.jsonl"
    families_path = output_dir / "families.json"
    _write_jsonl(raw_path, raw)
    _write_jsonl(reviewed_path, reviewed)

    label_counts = Counter(example.label for example in raw)
    family_counts = Counter(example.family_id for example in raw)
    source_counts = Counter(example.source.split(":", 1)[0] for example in raw)
    manifest = {
        "schema_version": DATASET_SCHEMA_VERSION,
        "labels": sorted(V1_DOMAINS),
        "signals": sorted(SIGNALS),
        "counts": {
            "collected": len(collected),
            "raw": len(raw),
            "reviewed": len(reviewed),
            "deduplicated": len(collected) - len(raw),
            "conflicts": len(conflicts),
        },
        "labels_count": dict(sorted(label_counts.items())),
        "families_count": dict(sorted(family_counts.items())),
        "sources_count": dict(sorted(source_counts.items())),
        "conflicts": conflicts,
        "skipped": {
            "unreviewed_feedback": "excluded",
            "test_results_directories": "excluded",
            "invalid_or_non_persian_text": "excluded",
            "sensitive_national_ids": "redacted",
        },
    }
    families_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return BuildResult(raw_path, reviewed_path, families_path, len(raw), len(reviewed))
