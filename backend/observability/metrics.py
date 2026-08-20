from dataclasses import dataclass
from .llm_events import LLMEvent, event_store


@dataclass(frozen=True)
class LLMMetrics:
    requests: int
    successful: int
    failed: int
    input_tokens: int
    output_tokens: int
    estimated_cost: float
    average_latency_ms: float


def current_metrics() -> LLMMetrics:
    events = event_store.snapshot()
    return LLMMetrics(
        requests=len(events),
        successful=sum(e.success for e in events),
        failed=sum(not e.success for e in events),
        input_tokens=sum(e.input_tokens for e in events),
        output_tokens=sum(e.output_tokens for e in events),
        estimated_cost=sum(e.estimated_cost for e in events),
        average_latency_ms=(sum(e.latency_ms for e in events) / len(events)) if events else 0.0,
    )

