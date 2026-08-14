from pathlib import Path

from backend.feedback.models import FeedbackRequest
from backend.feedback.service import FeedbackService
from backend.pipeline.models import PipelineResponse


def request(query_id: str, rating: str = "positive", **kwargs) -> FeedbackRequest:
    return FeedbackRequest(query_id=query_id, question="اطلاعات کارمند با کد ملی 8223876400", rating=rating, **kwargs)


def test_pipeline_response_has_unique_query_id():
    first = PipelineResponse(question="سؤال اول")
    second = PipelineResponse(question="سؤال دوم")
    assert first.query_id and first.query_id != second.query_id


def test_feedback_redacts_sensitive_identifier(tmp_path: Path):
    service = FeedbackService(tmp_path)
    service.submit("default", request("query-0001", selected_group="employees"))
    event = service.load("default")[0]
    assert "8223876400" not in event.question_redacted and "***" in event.question_redacted


def test_second_vote_replaces_previous_vote(tmp_path: Path):
    service = FeedbackService(tmp_path)
    service.submit("default", request("query-0001", selected_group="employees"))
    service.submit("default", request("query-0001", "negative", selected_group="employees"))
    events = service.load("default")
    assert len(events) == 1 and events[0].rating == "negative"


def test_feedback_adjustments_are_bounded_and_question_specific(tmp_path: Path):
    service = FeedbackService(tmp_path)
    service.submit("default", request("query-0001", "negative", selected_report="wrong", corrected_report="right"))
    adjustments = service.candidate_adjustments("default", "اطلاعات کارمند با کد ملی 8223876400", "report")
    assert adjustments == {"wrong": -0.06, "right": 0.08}
    assert service.candidate_adjustments("default", "یک سؤال دیگر", "report") == {}
    assert all(-0.15 <= score <= 0.15 for score in adjustments.values())


def test_feedback_summary(tmp_path: Path):
    service = FeedbackService(tmp_path)
    service.submit("default", request("query-0001", selected_group="employees"))
    service.submit("default", request("query-0002", "negative", corrected_group="students"))
    summary = service.summary("default")
    assert (summary.total, summary.positive, summary.negative) == (2, 1, 1)
    assert summary.satisfaction_rate == 50.0 and summary.corrections == 1
