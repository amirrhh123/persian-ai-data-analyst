from backend.database.discovery_service import schema_discovery_service
from backend.database.models import (
    DiscoveredColumnInfo,
    DiscoveredTableInfo,
    SchemaDiscoverySnapshot,
)


def test_schema_discovery_fingerprint_ignores_generated_at():
    table = DiscoveredTableInfo(
        schema_name="public",
        name="employees",
        row_count=1,
        columns=[
            DiscoveredColumnInfo(
                name="id",
                data_type="integer",
                udt_name="int4",
                is_nullable=False,
                is_primary_key=True,
            )
        ],
        primary_keys=["id"],
    )
    first = SchemaDiscoverySnapshot(
        tenant_id="education_ministry",
        database_name="persian_ai_db",
        schema_name="public",
        generated_at="2026-07-21T00:00:00",
        fingerprint="",
        tables=[table],
        relationships=[],
    )
    second = first.model_copy(update={"generated_at": "2026-07-21T01:00:00"})

    assert schema_discovery_service.calculate_fingerprint(first) == (
        schema_discovery_service.calculate_fingerprint(second)
    )


def test_schema_discovery_fingerprint_changes_for_schema_changes():
    base = SchemaDiscoverySnapshot(
        tenant_id="education_ministry",
        database_name="persian_ai_db",
        schema_name="public",
        generated_at="2026-07-21T00:00:00",
        fingerprint="",
        tables=[
            DiscoveredTableInfo(
                schema_name="public",
                name="employees",
                row_count=1,
                columns=[
                    DiscoveredColumnInfo(
                        name="id",
                        data_type="integer",
                        udt_name="int4",
                        is_nullable=False,
                        is_primary_key=True,
                    )
                ],
                primary_keys=["id"],
            )
        ],
        relationships=[],
    )
    changed = base.model_copy(
        update={
            "tables": [
                base.tables[0].model_copy(
                    update={
                        "columns": [
                            *base.tables[0].columns,
                            DiscoveredColumnInfo(
                                name="status",
                                data_type="character varying",
                                udt_name="varchar",
                            ),
                        ]
                    }
                )
            ]
        }
    )

    assert schema_discovery_service.calculate_fingerprint(base) != (
        schema_discovery_service.calculate_fingerprint(changed)
    )


def test_structure_fingerprint_ignores_data_samples():
    base = SchemaDiscoverySnapshot(
        tenant_id="education_ministry", database_name="persian_ai_db",
        generated_at="2026-07-21T00:00:00", fingerprint="", tables=[
            DiscoveredTableInfo(name="employees", row_count=1, columns=[
                DiscoveredColumnInfo(name="id", data_type="integer", udt_name="int4", is_primary_key=True)
            ], primary_keys=["id"])
        ], relationships=[]
    )
    changed = base.model_copy(update={"tables": [base.tables[0].model_copy(update={"row_count": 999, "sample_rows": [{"id": 999}]})]})
    assert schema_discovery_service.calculate_structure_fingerprint(base) == schema_discovery_service.calculate_structure_fingerprint(changed)
