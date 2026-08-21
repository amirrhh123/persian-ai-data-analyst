"""Safety and behavior tests for the bounded SQL repair loop."""

from backend.database.models import ColumnInfo, DatabaseSchema, TableInfo
from backend.pipeline.intent import QueryIntent
from backend.sql.repair_loop import SQLRepairLoop


def _schema() -> DatabaseSchema:
    return DatabaseSchema(tables=[
        TableInfo(
            name="employees",
            columns=[
                ColumnInfo(name="id", data_type="integer"),
                ColumnInfo(name="first_name", data_type="varchar"),
                ColumnInfo(name="national_id", data_type="varchar"),
            ],
        ),
        TableInfo(
            name="test1",
            columns=[ColumnInfo(name="id", data_type="integer")],
        ),
    ])


def test_expands_select_star_using_real_schema_columns() -> None:
    result = SQLRepairLoop().repair("SELECT * FROM employees", _schema())
    assert result.valid is True
    assert result.sql == (
        "SELECT employees.id, employees.first_name, employees.national_id FROM employees"
    )
    assert result.attempts[0].strategies == ["expand_select_star"]


def test_repairs_unique_numeric_table_suffix() -> None:
    result = SQLRepairLoop().repair("SELECT COUNT(test.id) FROM test", _schema())
    assert result.valid is True
    assert "test1.id" in result.sql
    assert "FROM test1" in result.sql


def test_quotes_unquoted_national_id() -> None:
    result = SQLRepairLoop().repair(
        "SELECT employees.id FROM employees WHERE employees.national_id = 1234567890",
        _schema(),
        intent=QueryIntent(requested_entity="employee", national_id="1234567890"),
    )
    assert result.valid is True
    assert "national_id = '1234567890'" in result.sql


def test_caps_excessive_limit() -> None:
    result = SQLRepairLoop().repair("SELECT employees.id FROM employees LIMIT 5000", _schema())
    assert result.valid is True
    assert result.sql.endswith("LIMIT 1000")


def test_never_repairs_forbidden_statement() -> None:
    sql = "DELETE FROM employees WHERE id = 1"
    result = SQLRepairLoop().repair(sql, _schema())
    assert result.valid is False
    assert result.sql == sql
    assert result.stopped_reason == "forbidden_statement"
    assert result.attempts == []


def test_stops_when_no_schema_grounded_repair_exists() -> None:
    sql = "SELECT employees.unknown_column FROM employees"
    result = SQLRepairLoop().repair(sql, _schema())
    assert result.valid is False
    assert result.stopped_reason == "no_safe_repair"


def test_returns_without_attempt_when_sql_is_already_valid() -> None:
    sql = "SELECT employees.id FROM employees"
    result = SQLRepairLoop().repair(sql, _schema())
    assert result.valid is True
    assert result.repaired is False
    assert result.stopped_reason == "already_valid"
