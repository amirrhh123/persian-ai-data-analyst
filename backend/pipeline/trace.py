from datetime import datetime
from typing import Optional, Dict, Any
from backend.pipeline.models import PipelineStep, PipelineTrace


class PipelineTracer:
    def __init__(self):
        self.steps: List[PipelineStep] = []
        self.start_time = datetime.now()
    
    def add_step(
        self,
        name: str,
        status: str,
        duration_ms: float = 0.0,
        data: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None
    ):
        step = PipelineStep(
            name=name,
            status=status,
            duration_ms=duration_ms,
            data=data,
            error=error
        )
        self.steps.append(step)
    
    def get_trace(self) -> PipelineTrace:
        total_duration = (datetime.now() - self.start_time).total_seconds() * 1000
        success = all(s.status != "error" for s in self.steps)
        
        return PipelineTrace(
            steps=self.steps,
            total_duration_ms=round(total_duration, 2),
            success=success
        )


from typing import List
