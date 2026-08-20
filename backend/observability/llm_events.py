from dataclasses import dataclass, asdict
from time import time
from typing import Any


@dataclass(frozen=True)
class LLMEvent:
    query_id: str
    provider: str
    model: str
    input_tokens: int
    output_tokens: int
    latency_ms: float
    estimated_cost: float
    success: bool
    cpu_time_ms: float | None = None
    gpu_time_ms: float | None = None
    memory_mb: float | None = None
    queue_time_ms: float | None = None
    created_at: float = 0.0

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class LLMEventStore:
    def __init__(self, max_events: int = 5000):
        self.max_events = max_events
        self.events: list[LLMEvent] = []

    def record(self, event: LLMEvent) -> LLMEvent:
        self.events.append(event)
        if len(self.events) > self.max_events:
            del self.events[:-self.max_events]
        return event

    def snapshot(self) -> list[LLMEvent]:
        return list(self.events)


event_store = LLMEventStore()

