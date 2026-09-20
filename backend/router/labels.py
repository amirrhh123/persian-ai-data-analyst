"""Router signal constants and domain labels for the Tiny Persian Intent Router."""

# Canonical V1 domains. These are the only valid values for RouterPrediction.domain.
V1_DOMAINS = frozenset({
    "student",
    "employee",
    "school",
    "salary",
    "organization",
    "retirement",
    "generic_semantic",
})

# Router signals — these are NOT domains and must never be accepted as RouterPrediction.domain.
SIGNAL_UNSAFE = "unsafe"
SIGNAL_AMBIGUOUS = "ambiguous"
SIGNAL_MULTI_INTENT = "multi_intent"
SIGNAL_RANKING = "ranking"

SIGNALS = frozenset({
    SIGNAL_UNSAFE,
    SIGNAL_AMBIGUOUS,
    SIGNAL_MULTI_INTENT,
    SIGNAL_RANKING,
})

_ALL_ROUTER_LABELS = V1_DOMAINS | SIGNALS


def is_domain(label: str) -> bool:
    """Return True if label is a canonical V1 domain."""
    return label in V1_DOMAINS


def is_signal(label: str) -> bool:
    """Return True if label is a router signal (not a domain)."""
    return label in SIGNALS


def validate_domain(domain: str) -> None:
    """Raise ValueError if domain is not a supported V1 domain."""
    if domain not in V1_DOMAINS:
        raise ValueError(
            f"domain '{domain}' is not a supported V1 domain. "
            f"Supported: {sorted(V1_DOMAINS)}"
        )
