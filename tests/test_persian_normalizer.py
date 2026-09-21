"""Contract tests for the shared Persian normalizer."""

from __future__ import annotations

import pytest

from backend.pipeline.intent import normalize_persian
from backend.text.normalizer import normalize_persian_text, normalize_search_text


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("دانش\u200cآموز", "دانش آموز"),
        ("علي كريمي", "علی کریمی"),
        ("مسئولۀ آموزش", "مسئوله آموزش"),
        ("  اطلاعات\t\n مدرسه  ", "اطلاعات مدرسه"),
        ("مُعَلِّم", "معلم"),
        ("\u200fتهران\u200e", "تهران"),
    ],
)
def test_normalize_persian_variants(raw: str, expected: str) -> None:
    assert normalize_persian_text(raw) == expected


def test_search_normalization_converts_digits_case_and_separators() -> None:
    assert normalize_search_text("Student_ID/۱۴۰۳") == "student id 1403"


def test_plain_normalization_preserves_digits_and_regular_hyphen() -> None:
    assert normalize_persian_text("سال ۱۴۰۳-۱۴۰۴") == "سال ۱۴۰۳-۱۴۰۴"


def test_non_string_is_rejected() -> None:
    with pytest.raises(TypeError):
        normalize_persian_text(123)  # type: ignore[arg-type]


def test_legacy_intent_api_uses_shared_contract() -> None:
    assert normalize_persian("دانش\u200cآموز يازدهم") == "دانش آموز یازدهم"

