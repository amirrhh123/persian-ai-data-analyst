"""Models used by the generic value index."""

from pydantic import BaseModel, Field


class ValueIndexEntry(BaseModel):
    """One safe categorical database value and its source."""

    table: str
    column: str
    value: str
    normalized_value: str
    count: int = 0
    column_aliases: list[str] = Field(default_factory=list)


class ValueIndexSnapshot(BaseModel):
    """A versioned value index derived from one schema fingerprint."""

    version: int = 1
    tenant_id: str
    source_fingerprint: str
    generated_at: str
    entries: list[ValueIndexEntry] = Field(default_factory=list)
    excluded_columns: dict[str, str] = Field(default_factory=dict)


class ValueIndexMatch(BaseModel):
    """A value mention found in a user question."""

    table: str
    column: str
    value: str
    count: int
    score: float
    label_matched: bool = False
    matched_label: str | None = None
