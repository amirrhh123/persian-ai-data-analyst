"""Canonical Persian text normalization used across the application."""

from __future__ import annotations

import re
import unicodedata


_CHARACTER_TRANSLATION = str.maketrans(
    {
        "ي": "ی",
        "ى": "ی",
        "ك": "ک",
        "ة": "ه",
        "ۀ": "ه",
        "ؤ": "و",
        "إ": "ا",
        "أ": "ا",
        "ٱ": "ا",
        "\u200e": "",
        "\u200f": "",
        "\ufeff": "",
        "\u00a0": " ",
        "\u200c": " ",
    }
)
_DIGIT_TRANSLATION = str.maketrans(
    {
        "۰": "0",
        "۱": "1",
        "۲": "2",
        "۳": "3",
        "۴": "4",
        "۵": "5",
        "۶": "6",
        "۷": "7",
        "۸": "8",
        "۹": "9",
        "٠": "0",
        "١": "1",
        "٢": "2",
        "٣": "3",
        "٤": "4",
        "٥": "5",
        "٦": "6",
        "٧": "7",
        "٨": "8",
        "٩": "9",
    }
)
_SEPARATORS_RE = re.compile(r"[_\-/]+")
_WHITESPACE_RE = re.compile(r"\s+")
_COMBINING_MARKS_RE = re.compile(r"[\u064b-\u065f\u0670]")


def normalize_persian_text(
    value: str,
    *,
    ascii_digits: bool = False,
    separators_as_space: bool = False,
    lowercase: bool = False,
) -> str:
    """Normalize Persian/Arabic variants without changing semantic content.

    Args:
        value: Input text. A non-string value is rejected to expose caller bugs.
        ascii_digits: Convert Persian and Arabic-Indic digits to ASCII.
        separators_as_space: Convert underscore, slash, and hyphen runs to spaces.
        lowercase: Apply Unicode-aware case folding for matching/indexing.

    Returns:
        Canonically normalized text with collapsed whitespace.

    Raises:
        TypeError: If ``value`` is not a string.
    """
    if not isinstance(value, str):
        raise TypeError("value must be a string")
    normalized = unicodedata.normalize("NFKC", value).translate(_CHARACTER_TRANSLATION)
    normalized = _COMBINING_MARKS_RE.sub("", normalized)
    if ascii_digits:
        normalized = normalized.translate(_DIGIT_TRANSLATION)
    if separators_as_space:
        normalized = _SEPARATORS_RE.sub(" ", normalized)
    if lowercase:
        normalized = normalized.casefold()
    return _WHITESPACE_RE.sub(" ", normalized).strip()


def normalize_search_text(value: str) -> str:
    """Normalize text for lexical search, hashing, and exact matching."""
    return normalize_persian_text(
        value,
        ascii_digits=True,
        separators_as_space=True,
        lowercase=True,
    )

