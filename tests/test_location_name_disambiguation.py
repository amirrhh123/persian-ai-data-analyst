import pytest

from backend.pipeline.models import PipelineRequest
from backend.pipeline.query_pipeline import query_pipeline


@pytest.mark.asyncio
async def test_city_word_inside_school_name_is_not_location_filter():
    response = await query_pipeline.execute(
        PipelineRequest(question="اطلاعات مدرسه دبستان امید شیراز", execute=False)
    )

    assert response.valid is True
    assert response.intent["named_school"] == "دبستان امید شیراز"
    assert response.intent["province"] is None
    assert response.intent["city"] is None
    assert "schools.name = 'دبستان امید شیراز'" in response.sql
    assert "organization_units.province" not in response.sql
    assert "organization_units.city" not in response.sql


@pytest.mark.asyncio
async def test_explicit_city_filter_uses_city_not_province():
    response = await query_pipeline.execute(
        PipelineRequest(question="مدارس شهر تهران را نشان بده", execute=False)
    )

    assert response.valid is True
    assert response.intent["province"] is None
    assert response.intent["city"] == "تهران"
    assert "organization_units.city = 'تهران'" in response.sql
    assert "organization_units.province = 'تهران'" not in response.sql
