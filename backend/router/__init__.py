"""Tiny Persian Intent Router — stable public contract.

Exports:
    RouterPrediction: Frozen dataclass with validated prediction fields.
    V1_DOMAINS: Immutable frozenset of canonical domain labels.
    SIGNAL_UNSAFE, SIGNAL_AMBIGUOUS, SIGNAL_MULTI_INTENT, SIGNAL_RANKING: Router signal constants.
    SIGNALS: Immutable frozenset of all router signal labels.
    is_domain, is_signal, validate_domain: Label validation helpers.
"""

from backend.router.labels import (
    SIGNALS,
    SIGNAL_AMBIGUOUS,
    SIGNAL_MULTI_INTENT,
    SIGNAL_RANKING,
    SIGNAL_UNSAFE,
    V1_DOMAINS,
    is_domain,
    is_signal,
    validate_domain,
)
from backend.router.models import RouterPrediction

__all__ = [
    "RouterPrediction",
    "V1_DOMAINS",
    "SIGNAL_UNSAFE",
    "SIGNAL_AMBIGUOUS",
    "SIGNAL_MULTI_INTENT",
    "SIGNAL_RANKING",
    "SIGNALS",
    "is_domain",
    "is_signal",
    "validate_domain",
]
