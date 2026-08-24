"""In-memory clarification state (roadmap Change 5).

When the pipeline asks a Persian clarification question it stores what it knew
(original question, candidate interpretations, missing decision) so the next
message in the same session RESUMES the original request instead of starting
over. Deliberately in-memory first; durable checkpoints arrive with LangGraph
(Phase 8) and must respect redaction rules.
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


_TTL_SECONDS = 30 * 60
_MAX_ENTRIES = 512


class ClarificationContext(BaseModel):
    """Everything needed to resume an ambiguous request."""

    session_id: str
    original_question: str
    candidates: List[Dict[str, Any]] = Field(default_factory=list)
    missing_decision: str = ""
    created_at: float = Field(default_factory=time.time)

    def touch(self) -> None:
        self.created_at = time.time()


class InMemoryClarificationStore:
    def __init__(self, ttl_seconds: int = _TTL_SECONDS, max_entries: int = _MAX_ENTRIES) -> None:
        self._ttl = ttl_seconds
        self._max = max_entries
        self._items: Dict[str, ClarificationContext] = {}

    def _evict_expired(self) -> None:
        now = time.time()
        expired = [key for key, item in self._items.items() if now - item.created_at > self._ttl]
        for key in expired:
            self._items.pop(key, None)

    def save(self, context: ClarificationContext) -> None:
        self._evict_expired()
        if len(self._items) >= self._max:
            oldest_key = min(self._items.items(), key=lambda kv: kv[1].created_at)[0]
            self._items.pop(oldest_key, None)
        self._items[context.session_id] = context

    def peek(self, session_id: str) -> Optional[ClarificationContext]:
        self._evict_expired()
        return self._items.get(session_id)

    def pop(self, session_id: str) -> Optional[ClarificationContext]:
        self._evict_expired()
        return self._items.pop(session_id, None)

    def clear(self) -> None:
        self._items.clear()


clarification_store = InMemoryClarificationStore()
