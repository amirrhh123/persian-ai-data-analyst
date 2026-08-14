from backend.database.models import ColumnInfo, DatabaseSchema, TableInfo
from backend.sql.identifier_canonicalizer import canonicalize_sql_identifiers


def _schema(*table_names: str) -> DatabaseSchema:
    return DatabaseSchema(
        tables=[
            TableInfo(
                name=table_name,
                columns=[ColumnInfo(name="id", data_type="integer")],
                primary_keys=["id"],
            )
            for table_name in table_names
        ]
    )


def test_canonicalizes_unknown_table_to_unique_numeric_suffix_table() -> None:
    sql = "SELECT COUNT(test.id) AS count FROM test"

    canonical_sql, report = canonicalize_sql_identifiers(sql, _schema("test1"))

    assert canonical_sql == "SELECT COUNT(test1.id) AS count FROM test1"
    assert report == {"changed": True, "replacements": {"test": "test1"}}


def test_does_not_canonicalize_ambiguous_numeric_suffix_tables() -> None:
    sql = "SELECT COUNT(test.id) AS count FROM test"

    canonical_sql, report = canonicalize_sql_identifiers(sql, _schema("test1", "test2"))

    assert canonical_sql == sql
    assert report == {"changed": False, "replacements": {}}


def test_does_not_touch_valid_table_names() -> None:
    sql = "SELECT COUNT(test1.id) AS count FROM test1"

    canonical_sql, report = canonicalize_sql_identifiers(sql, _schema("test1"))

    assert canonical_sql == sql
    assert report == {"changed": False, "replacements": {}}
