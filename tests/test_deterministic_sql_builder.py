from backend.pipeline.intent import NormalizedIntent, NormalizedIntentFilter
from backend.semantic.models import SemanticCatalog, SemanticColumn, SemanticJoin, SemanticTable
from backend.sql.deterministic_builder import deterministic_sql_builder
from backend.sql.templates import render_template_sql


def _catalog() -> SemanticCatalog:
    return SemanticCatalog(
        tables=[
            SemanticTable(
                name="students",
                entity="student",
                description="students",
                default_display_columns=["first_name", "last_name", "grade"],
                columns=[
                    SemanticColumn(name="id", data_type="integer", description="id"),
                    SemanticColumn(name="first_name", data_type="text", description="first"),
                    SemanticColumn(name="last_name", data_type="text", description="last"),
                    SemanticColumn(name="national_id", data_type="text", description="nid", pii=True),
                    SemanticColumn(name="school_id", data_type="integer", description="school"),
                    SemanticColumn(name="grade", data_type="text", description="grade"),
                    SemanticColumn(name="status", data_type="text", description="status"),
                ],
            ),
            SemanticTable(
                name="employees",
                entity="employee",
                description="employees",
                default_display_columns=["first_name", "last_name", "position", "status"],
                columns=[
                    SemanticColumn(name="id", data_type="integer", description="id"),
                    SemanticColumn(name="first_name", data_type="text", description="first"),
                    SemanticColumn(name="last_name", data_type="text", description="last"),
                    SemanticColumn(name="national_id", data_type="text", description="nid", pii=True),
                    SemanticColumn(name="position", data_type="text", description="position"),
                    SemanticColumn(name="status", data_type="text", description="status"),
                    SemanticColumn(name="organization_unit_id", data_type="integer", description="org"),
                ],
            ),
            SemanticTable(
                name="schools",
                entity="school",
                description="schools",
                default_display_columns=["name", "school_type"],
                columns=[
                    SemanticColumn(name="id", data_type="integer", description="id"),
                    SemanticColumn(name="name", data_type="text", description="name"),
                    SemanticColumn(name="school_type", data_type="text", description="type"),
                    SemanticColumn(name="organization_unit_id", data_type="integer", description="org"),
                ],
            ),
            SemanticTable(
                name="organization_units",
                entity="organization_unit",
                description="orgs",
                default_display_columns=["name", "province", "city"],
                columns=[
                    SemanticColumn(name="id", data_type="integer", description="id"),
                    SemanticColumn(name="name", data_type="text", description="name"),
                    SemanticColumn(name="province", data_type="text", description="province"),
                    SemanticColumn(name="city", data_type="text", description="city"),
                ],
            ),
        ],
        joins=[
            SemanticJoin(
                from_table="students",
                from_column="school_id",
                to_table="schools",
                to_column="id",
                description="student school",
            ),
            SemanticJoin(
                from_table="schools",
                from_column="organization_unit_id",
                to_table="organization_units",
                to_column="id",
                description="school org",
            ),
            SemanticJoin(
                from_table="employees",
                from_column="organization_unit_id",
                to_table="organization_units",
                to_column="id",
                description="employee org",
            ),
        ],
    )


def test_deterministic_builder_student_count_by_province(monkeypatch):
    import backend.sql.templates as templates

    catalog = _catalog()
    monkeypatch.setattr(templates, "semantic_catalog", catalog)
    normalized = NormalizedIntent(
        entity="student",
        operation="count",
        filters=[NormalizedIntentFilter(field="province", value="تهران")],
        metrics=["*"],
        confidence=0.9,
    )

    plan = deterministic_sql_builder.build(normalized, catalog)
    sql = render_template_sql(plan)

    assert plan.selected_columns == ["GENERIC_TABLE_COUNT"]
    assert plan.planning_source == "deterministic_normalized_intent"
    assert plan.required_tables == ["students", "schools", "organization_units"]
    assert "JOIN schools ON students.school_id = schools.id" in sql
    assert "organization_units.province = 'تهران'" in sql
    assert "COUNT(students.id)" in sql


def test_deterministic_builder_employee_profile_by_national_id(monkeypatch):
    catalog = _catalog()
    normalized = NormalizedIntent(
        entity="employee",
        operation="profile",
        filters=[NormalizedIntentFilter(field="national_id", value="4871587050")],
        confidence=0.9,
    )

    assert deterministic_sql_builder.build(normalized, catalog) is None


def test_deterministic_builder_school_list_by_province(monkeypatch):
    catalog = _catalog()
    normalized = NormalizedIntent(
        entity="school",
        operation="list",
        filters=[NormalizedIntentFilter(field="province", value="تهران")],
        requested_columns=["name"],
        confidence=0.85,
    )

    assert deterministic_sql_builder.build(normalized, catalog) is None


def test_deterministic_builder_defers_multi_value_location_filters():
    catalog = _catalog()
    normalized = NormalizedIntent(
        entity="student",
        operation="count",
        filters=[
            NormalizedIntentFilter(field="province", value="تهران"),
            NormalizedIntentFilter(field="province", value="اصفهان"),
        ],
        confidence=0.9,
    )

    assert deterministic_sql_builder.build(normalized, catalog) is None


def test_deterministic_builder_defers_student_profile_with_broad_filters_to_legacy_templates():
    catalog = _catalog()
    normalized = NormalizedIntent(
        entity="student",
        operation="profile",
        filters=[
            NormalizedIntentFilter(field="province", value="ØªÙ‡Ø±Ø§Ù†"),
            NormalizedIntentFilter(field="grade", value="ÛŒØ§Ø²Ø¯Ù‡Ù…"),
        ],
        confidence=0.9,
    )

    assert deterministic_sql_builder.build(normalized, catalog) is None


def test_deterministic_builder_defers_student_profile_by_national_id_to_legacy_templates():
    catalog = _catalog()
    normalized = NormalizedIntent(
        entity="student",
        operation="profile",
        filters=[NormalizedIntentFilter(field="national_id", value="3489881390")],
        confidence=0.9,
    )

    assert deterministic_sql_builder.build(normalized, catalog) is None
