import pytest

from backend.pipeline.models import PipelineRequest
from backend.pipeline.query_pipeline import query_pipeline


@pytest.mark.asyncio
async def test_school_profile_uses_schools_table_not_organization_units():
    response = await query_pipeline.execute(
        PipelineRequest(question="اطلاعات مدرسه دبیرستان فرزانگان", execute=False)
    )

    assert response.valid is True
    assert response.intent["named_school"] == "دبیرستان فرزانگان"
    assert "FROM schools" in response.sql
    assert "schools.name = 'دبیرستان فرزانگان'" in response.sql
    assert "FROM organization_units" not in response.sql


@pytest.mark.asyncio
async def test_school_count_by_named_educational_region_filters_org_unit_name():
    response = await query_pipeline.execute(
        PipelineRequest(question="تعداد مدارس منطقه آموزشی یک تهران", execute=False)
    )

    assert response.valid is True
    assert response.intent["named_organization_unit"] == "منطقه آموزشی یک تهران"
    assert response.intent["province"] is None
    assert "FROM schools" in response.sql
    assert "JOIN organization_units ON schools.organization_unit_id = organization_units.id" in response.sql
    assert "organization_units.name = 'منطقه آموزشی یک تهران'" in response.sql
    assert "organization_units.province = 'تهران'" not in response.sql


@pytest.mark.asyncio
async def test_organization_unit_profile_uses_organization_units_table():
    response = await query_pipeline.execute(
        PipelineRequest(question="اطلاعات واحد سازمانی اداره کل آموزش و پرورش تهران", execute=False)
    )

    assert response.valid is True
    assert response.group == "organization"
    assert response.intent["named_organization_unit"] == "اداره کل آموزش و پرورش تهران"
    assert "FROM organization_units" in response.sql
    assert "organization_units.name = 'اداره کل آموزش و پرورش تهران'" in response.sql
    assert "FROM schools" not in response.sql
