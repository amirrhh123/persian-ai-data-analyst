from backend.sql.models import SQLPlan
from backend.sql.templates import render_template_sql, sql_literal
from backend.semantic.models import SemanticCatalog, SemanticColumn, SemanticTable


def test_sql_literal_escapes_single_quotes():
    assert sql_literal("مدرسه O'Reilly") == "'مدرسه O''Reilly'"


def test_employee_by_national_id_uses_requested_column_whitelist():
    plan = SQLPlan(
        required_tables=["employees"],
        selected_columns=[
            "EMPLOYEE_BY_NATIONAL_ID",
            "national_id",
            "first_name",
            "last_name",
            "made_up_column",
        ],
        filters=[{"column": "national_id", "operator": "=", "value": "4871587050"}],
    )

    sql = render_template_sql(plan)

    assert sql == (
        "SELECT employees.national_id, employees.first_name, employees.last_name "
        "FROM employees WHERE employees.national_id = '4871587050'"
    )
    assert "made_up_column" not in sql


def test_school_phone_template_escapes_name_literal():
    plan = SQLPlan(
        required_tables=["schools"],
        selected_columns=["SCHOOL_PHONE_BY_NAME"],
        filters=[{"column": "name", "operator": "=", "value": "دبیرستان شهید 'بهشتی'"}],
    )

    sql = render_template_sql(plan)

    assert "schools.name = 'دبیرستان شهید ''بهشتی'''" in sql


def test_student_count_by_province_template_uses_required_join_path():
    plan = SQLPlan(
        required_tables=["students", "schools", "organization_units"],
        selected_columns=["STUDENT_COUNT_BY_PROVINCE"],
        filters=[{"column": "province", "operator": "=", "value": "تهران"}],
    )

    sql = render_template_sql(plan)

    assert "FROM students" in sql
    assert "JOIN schools ON students.school_id = schools.id" in sql
    assert "JOIN organization_units ON schools.organization_unit_id = organization_units.id" in sql
    assert "organization_units.province = 'تهران'" in sql


def test_generic_count_template_supports_joined_filter_table():
    plan = SQLPlan(
        required_tables=["students", "schools", "organization_units"],
        joins=[
            {
                "from_table": "students",
                "from_column": "school_id",
                "to_table": "schools",
                "to_column": "id",
            },
            {
                "from_table": "schools",
                "from_column": "organization_unit_id",
                "to_table": "organization_units",
                "to_column": "id",
            },
        ],
        selected_columns=["GENERIC_TABLE_COUNT"],
        filters=[{"column": "organization_units.province", "operator": "=", "value": "تهران"}],
        aggregations=[{"function": "COUNT", "column": "students.id"}],
    )

    sql = render_template_sql(plan)

    assert sql == (
        "SELECT COUNT(students.id) AS row_count "
        "FROM students "
        "JOIN schools ON students.school_id = schools.id "
        "JOIN organization_units ON schools.organization_unit_id = organization_units.id "
        "WHERE organization_units.province = 'تهران'"
    )


def test_generic_list_template_supports_joined_filter_table():
    plan = SQLPlan(
        required_tables=["students", "schools", "organization_units"],
        joins=[
            {
                "from_table": "students",
                "from_column": "school_id",
                "to_table": "schools",
                "to_column": "id",
            },
            {
                "from_table": "schools",
                "from_column": "organization_unit_id",
                "to_table": "organization_units",
                "to_column": "id",
            },
        ],
        selected_columns=["GENERIC_TABLE_LIST", "first_name", "last_name"],
        filters=[{"column": "province", "operator": "=", "value": "تهران"}],
    )

    sql = render_template_sql(plan)

    assert "SELECT students.first_name, students.last_name FROM students" in sql
    assert "JOIN schools ON students.school_id = schools.id" in sql
    assert "JOIN organization_units ON schools.organization_unit_id = organization_units.id" in sql
    assert "WHERE organization_units.province = 'تهران'" in sql
    assert "ORDER BY students.id" in sql


def test_generic_count_template_supports_group_by_column():
    plan = SQLPlan(
        required_tables=["demo_training_requests"],
        selected_columns=["GENERIC_TABLE_COUNT"],
        group_by=["status"],
    )

    sql = render_template_sql(plan)

    assert sql == (
        "SELECT demo_training_requests.status, COUNT(demo_training_requests.id) AS row_count "
        "FROM demo_training_requests "
        "GROUP BY demo_training_requests.status ORDER BY demo_training_requests.status"
    )


def test_generic_aggregate_template_supports_sum_with_group_by():
    plan = SQLPlan(
        required_tables=["demo_training_requests"],
        selected_columns=["GENERIC_TABLE_AGGREGATE"],
        aggregations=[{"function": "SUM", "column": "estimated_cost"}],
        group_by=["status"],
    )

    sql = render_template_sql(plan)

    assert sql == (
        "SELECT demo_training_requests.status, SUM(demo_training_requests.estimated_cost) AS sum_estimated_cost "
        "FROM demo_training_requests "
        "GROUP BY demo_training_requests.status ORDER BY demo_training_requests.status"
    )


def test_generic_aggregate_template_supports_avg_without_group_by():
    plan = SQLPlan(
        required_tables=["demo_training_requests"],
        selected_columns=["GENERIC_TABLE_AGGREGATE"],
        aggregations=[{"function": "AVG", "column": "estimated_cost"}],
    )

    sql = render_template_sql(plan)

    assert sql == (
        "SELECT AVG(demo_training_requests.estimated_cost) AS avg_estimated_cost "
        "FROM demo_training_requests"
    )


def test_generic_list_template_supports_order_by_and_limit():
    plan = SQLPlan(
        required_tables=["demo_training_requests"],
        selected_columns=["GENERIC_TABLE_LIST", "requester_name", "estimated_cost"],
        order_by="estimated_cost DESC",
        limit=1,
    )

    sql = render_template_sql(plan)

    assert sql == (
        "SELECT demo_training_requests.requester_name, demo_training_requests.estimated_cost "
        "FROM demo_training_requests "
        "ORDER BY demo_training_requests.estimated_cost DESC LIMIT 1"
    )


def test_generic_list_template_applies_default_limit():
    plan = SQLPlan(
        required_tables=["demo_training_requests"],
        selected_columns=["GENERIC_TABLE_LIST", "requester_name"],
    )

    sql = render_template_sql(plan)

    assert sql.endswith("ORDER BY demo_training_requests.id LIMIT 1000")


def test_generic_list_template_supports_qualified_projection():
    plan = SQLPlan(
        required_tables=["students", "schools", "organization_units"],
        joins=[
            {
                "from_table": "students",
                "from_column": "school_id",
                "to_table": "schools",
                "to_column": "id",
            },
            {
                "from_table": "schools",
                "from_column": "organization_unit_id",
                "to_table": "organization_units",
                "to_column": "id",
            },
        ],
        selected_columns=["GENERIC_TABLE_LIST", "first_name", "organization_units.province"],
    )

    sql = render_template_sql(plan)

    assert sql.startswith("SELECT students.first_name, organization_units.province FROM students")
    assert "JOIN organization_units ON schools.organization_unit_id = organization_units.id" in sql


def test_generic_default_projection_excludes_pii_columns(monkeypatch):
    import backend.sql.templates as templates

    monkeypatch.setattr(
        templates,
        "semantic_catalog",
        SemanticCatalog(
            tables=[
                SemanticTable(
                    name="people",
                    entity="person",
                    description="people",
                    primary_key="id",
                    default_display_columns=["name", "national_id"],
                    columns=[
                        SemanticColumn(name="id", data_type="integer", description="id"),
                        SemanticColumn(name="name", data_type="text", description="name"),
                        SemanticColumn(name="national_id", data_type="text", description="national id", pii=True),
                    ],
                )
            ]
        ),
    )
    plan = SQLPlan(required_tables=["people"], selected_columns=["GENERIC_TABLE_LIST"])

    sql = render_template_sql(plan)

    assert "people.name" in sql
    assert "people.national_id" not in sql


def test_generic_explicit_projection_allows_requested_pii_column(monkeypatch):
    import backend.sql.templates as templates

    monkeypatch.setattr(
        templates,
        "semantic_catalog",
        SemanticCatalog(
            tables=[
                SemanticTable(
                    name="people",
                    entity="person",
                    description="people",
                    primary_key="id",
                    default_display_columns=["name"],
                    columns=[
                        SemanticColumn(name="id", data_type="integer", description="id"),
                        SemanticColumn(name="name", data_type="text", description="name"),
                        SemanticColumn(name="national_id", data_type="text", description="national id", pii=True),
                    ],
                )
            ]
        ),
    )
    plan = SQLPlan(required_tables=["people"], selected_columns=["GENERIC_TABLE_LIST", "national_id"])

    sql = render_template_sql(plan)

    assert "SELECT people.national_id FROM people" in sql


def test_generic_filter_where_supports_temporal_year_and_month():
    plan = SQLPlan(
        required_tables=["demo_training_requests"],
        selected_columns=["GENERIC_TABLE_COUNT"],
        filters=[
            {"column": "requested_at", "operator": "YEAR=", "value": "2026"},
            {"column": "requested_at", "operator": "MONTH=", "value": "7"},
        ],
    )

    sql = render_template_sql(plan)

    assert "EXTRACT(YEAR FROM demo_training_requests.requested_at) = 2026" in sql
    assert "EXTRACT(MONTH FROM demo_training_requests.requested_at) = 7" in sql


def test_generic_filter_where_supports_relative_temporal_filters():
    plan = SQLPlan(
        required_tables=["demo_training_requests"],
        selected_columns=["GENERIC_TABLE_COUNT"],
        filters=[
            {"column": "requested_at", "operator": "YEAR_CURRENT", "value": ""},
            {"column": "created_at", "operator": "DAYS_AGO", "value": "30"},
            {"column": "created_at", "operator": "DATE=", "value": "CURRENT_DATE"},
        ],
    )

    sql = render_template_sql(plan)

    assert "EXTRACT(YEAR FROM demo_training_requests.requested_at) = EXTRACT(YEAR FROM CURRENT_DATE)" in sql
    assert "demo_training_requests.created_at >= CURRENT_DATE - INTERVAL '30 days'" in sql
    assert "demo_training_requests.created_at::date = CURRENT_DATE" in sql


def test_generic_filter_where_supports_previous_month_filter():
    plan = SQLPlan(
        required_tables=["demo_training_requests"],
        selected_columns=["GENERIC_TABLE_COUNT"],
        filters=[{"column": "requested_at", "operator": "PREVIOUS_MONTH", "value": ""}],
    )

    sql = render_template_sql(plan)

    assert "demo_training_requests.requested_at >= date_trunc('month', CURRENT_DATE - INTERVAL '1 month')" in sql
    assert "demo_training_requests.requested_at < date_trunc('month', CURRENT_DATE)" in sql
