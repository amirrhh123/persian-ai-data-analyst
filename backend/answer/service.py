from typing import Dict, Any
from backend.answer.models import AnswerRequest, AnswerResponse
from backend.answer.generator import answer_generator
from backend.answer.formatter import result_formatter


class AnswerService:
    def __init__(self):
        self.generator = answer_generator
        self.formatter = result_formatter
    
    async def generate_answer(
        self,
        question: str,
        result: Dict[str, Any],
        report_name: str = "",
        group_name: str = ""
    ) -> AnswerResponse:
        request = AnswerRequest(
            question=question,
            result=result,
            report_name=report_name,
            group_name=group_name
        )
        
        return await self.generator.generate(request)
    
    def format_only(
        self,
        result: Dict[str, Any],
        report_name: str = ""
    ) -> Dict[str, Any]:
        formatted = self.formatter.format_result(result, report_name)
        return formatted.model_dump()


answer_service = AnswerService()
