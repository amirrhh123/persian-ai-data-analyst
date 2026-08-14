from backend.pipeline.intent import NormalizedIntent, NormalizedIntentFilter
from backend.semantic.models import SemanticCatalog, SemanticColumn, SemanticJoin, SemanticTable
from backend.sql.join_verifier import sql_plan_join_verifier
from backend.sql.models import SQLPlan


def _catalog() -> SemanticCatalog:
    return SemanticCatalog(
        tables=[
            SemanticTable(
                name="students",
                entity="student",
                description="students",
                columns=[
                    SemanticColumn(name="id", data_type="integer", description="id"),
                    SemanticColumn(name="school_id", data_type="integer", description="school"),
                ],
            ),
            SemanticTable(
                name="schools",
                entity="school",
                description="schools",
                columns=[
                    SemanticColumn(name="id", data_type="integer", description="id"),
                    SemanticColumn(name="organization_unit_id", data_type="integer", description="org"),
                ],
            ),
            SemanticTable(
                name="organization_units",
                entity="organization_unit",
                description="org",
                columns=[SemanticColumn(name="id", data_type="integer", description="id")],
            ),
            SemanticTable(
                name="employees",
                entity="employee",
                description="employees",
                columns=[
                    SemanticColumn(name="id", data_type="integer", description="id"),
                    SemanticColumn(name="organization_unit_id", data_type="integer", description="org"),
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
            SemanticJoin(
                from_table="organization_units",
                from_column="parent_id",
                to_table="organization_units",
                to_column="id",
                description="organization hierarchy",
            ),
        ],
    )


def test_join_verifier_accepts_complete_student_province_path():
    plan = SQLPlan(
        required_tables=["students", "schools", "organization_units"],
        joins=[
            {"from_table": "students", "from_column": "school_id", "to_table": "schools", "to_column": "id"},
            {
                "from_table": "schools",
                "from_column": "organization_unit_id",
                "to_table": "organization_units",
                "to_column": "id",
            },
        ],
    )
    normalized = NormalizedIntent(
        entity="student",
        operation="count",
        filters=[NormalizedIntentFilter(field="province", value="تهران")],
        confidence=0.9,
    )

    result = sql_plan_join_verifier.verify(plan, _catalog(), normalized)

    assert result.is_valid is True
    assert result.errors == []


def test_join_verifier_rejects_missing_intermediate_table_for_student_province():
    plan = SQLPlan(
        required_tables=["students", "organization_units"],
        joins=[],
    )
    normalized = NormalizedIntent(
        entity="student",
        operation="count",
        filters=[NormalizedIntentFilter(field="province", value="تهران")],
        confidence=0.9,
    )

    result = sql_plan_join_verifier.verify(plan, _catalog(), normalized)

    assert result.is_valid is False
    assert "schools" in result.missing_tables
    assert result.suggested_joins


def test_join_verifier_rejects_disconnected_required_tables():
    plan = SQLPlan(
        required_tables=["students", "schools", "employees"],
        joins=[{"from_table": "students", "from_column": "school_id", "to_table": "schools", "to_column": "id"}],
    )

    result = sql_plan_join_verifier.verify(plan, _catalog())

    assert result.is_valid is False
    assert "employees" in result.disconnected_tables


def test_join_verifier_warns_on_duplicate_joins():
    join = {"from_table": "students", "from_column": "school_id", "to_table": "schools", "to_column": "id"}
    plan = SQLPlan(
        required_tables=["students", "schools"],
        joins=[join, dict(join)],
    )

    result = sql_plan_join_verifier.verify(plan, _catalog())

    assert result.is_valid is True
    assert result.warnings


def test_join_detection_skips_unaliased_self_relationship_for_student_province_path():
    from backend.database.models import RelationshipInfo
    from backend.sql.planner import sql_planner

    relationships = [
        RelationshipInfo(
            source_table=join.from_table,
            source_column=join.from_column,
            target_table=join.to_table,
            target_column=join.to_column,
        )
        for join in _catalog().joins
    ]

    joins = sql_planner.detect_joins(["students", "schools", "organization_units"], relationships)
    plan = SQLPlan(
        required_tables=["students", "schools", "organization_units"],
        joins=joins,
    )
    normalized = NormalizedIntent(
        entity="student",
        operation="count",
        filters=[NormalizedIntentFilter(field="province", value="ØªÙ‡Ø±Ø§Ù†")],
        confidence=0.9,
    )

    result = sql_plan_join_verifier.verify(plan, _catalog(), normalized)

    assert result.is_valid is True
    assert all(join["from_table"] != join["to_table"] for join in joins)
