"""Tiny Persian Intent Router — frozen prediction model."""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from backend.router.labels import V1_DOMAINS, validate_domain


@dataclass(frozen=True)
class RouterPrediction:
    """Immutable router prediction with validated domain and probability fields.

    Fields:
        domain: Canonical V1 domain label.
        confidence: Scalar confidence in [0.0, 1.0].
        probabilities: Mapping from domain label to probability in [0.0, 1.0].
        accepted: Whether the router accepted the prediction.
        model_version: Non-empty model version identifier.
        latency_ms: Non-negative inference latency in milliseconds.
    """

    domain: str
    confidence: float
    probabilities: dict[str, float]
    accepted: bool
    model_version: str
    latency_ms: float

    def __post_init__(self) -> None:
        if not isinstance(self.domain, str):
            raise TypeError("domain must be a string")
        validate_domain(self.domain)

        if isinstance(self.confidence, bool) or not isinstance(self.confidence, (int, float)):
            raise TypeError("confidence must be a real number, not bool")
        if not math.isfinite(self.confidence):
            raise ValueError("confidence must be finite")
        if not (0.0 <= self.confidence <= 1.0):
            raise ValueError(
                f"confidence {self.confidence} must be in [0.0, 1.0]"
            )

        if not isinstance(self.probabilities, dict):
            raise TypeError("probabilities must be a dict[str, float]")
        for key, val in self.probabilities.items():
            if key not in V1_DOMAINS:
                raise ValueError(
                    f"probability key '{key}' is not a supported V1 domain"
                )
            if isinstance(val, bool) or not isinstance(val, (int, float)):
                raise TypeError(f"probability value for '{key}' must be a real number, not bool")
            if not math.isfinite(val):
                raise ValueError(f"probability value for '{key}' must be finite")
            if not (0.0 <= val <= 1.0):
                raise ValueError(
                    f"probability value {val} for key '{key}' must be in [0.0, 1.0]"
                )

        if not isinstance(self.accepted, bool):
            raise TypeError("accepted must be a bool")

        if not isinstance(self.model_version, str):
            raise TypeError("model_version must be a string")
        if not self.model_version or not self.model_version.strip():
            raise ValueError("model_version must be non-empty")

        if isinstance(self.latency_ms, bool) or not isinstance(self.latency_ms, (int, float)):
            raise TypeError("latency_ms must be a real number, not bool")
        if not math.isfinite(self.latency_ms):
            raise ValueError("latency_ms must be finite")
        if self.latency_ms < 0.0:
            raise ValueError(
                f"latency_ms {self.latency_ms} must be non-negative"
            )

    @staticmethod
    def create(
        domain: str,
        confidence: float,
        probabilities: dict[str, float],
        accepted: bool,
        model_version: str,
        latency_ms: float,
    ) -> RouterPrediction:
        """Type-annotated factory constructor for RouterPrediction."""
        return RouterPrediction(
            domain=domain,
            confidence=confidence,
            probabilities=probabilities,
            accepted=accepted,
            model_version=model_version,
            latency_ms=latency_ms,
        )
