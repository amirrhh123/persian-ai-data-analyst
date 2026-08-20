import re


def redact_sensitive(text: str) -> str:
    """Remove common national-ID, phone and email patterns before logging."""
    text = re.sub(r"\b\d{10}\b", "[REDACTED_ID]", text)
    text = re.sub(r"\b(?:09\d{9}|\+98\d{10})\b", "[REDACTED_PHONE]", text)
    return re.sub(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", "[REDACTED_EMAIL]", text)

