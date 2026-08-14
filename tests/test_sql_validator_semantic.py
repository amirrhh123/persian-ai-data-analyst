from backend.database.models import ColumnInfo, DatabaseSchema, TableInfo
from backend.pipeline.intent import QueryIntent
from backend.sql.validator import SQLValidator


def _schema() -> DatabaseSchema:
    return DatabaseSchema(
        tables=[
            TableInfo(
                name="employees",
                columns=[
                    ColumnInfo(name="id", data_type="integer"),
                    ColumnInfo(name="national_id", data_type="character varying"),
                    ColumnInfo(name="first_name", data_type="character varying"),
                    ColumnInfo(name="last_name", data_type="character varying"),
                    ColumnInfo(name="position", data_type="character varying"),
                    ColumnInfo(name="status", data_type="character varying"),
                    ColumnInfo(name="organization_unit_id", data_type="integer"),
                ],
            ),
            TableInfo(
                name="students",
                columns=[
                    ColumnInfo(name="id", data_type="integer"),
                    ColumnInfo(name="first_name", data_type="character varying"),
                    ColumnInfo(name="school_id", data_type="integer"),
                ],
            ),
            TableInfo(
                name="schools",
                columns=[
                    ColumnInfo(name="id", data_type="integer"),
                    ColumnInfo(name="name", data_type="character varying"),
                    ColumnInfo(name="phone", data_type="character varying"),
                    ColumnInfo(name="organization_unit_id", data_type="integer"),
                ],
            ),
            TableInfo(
                name="test1",
                columns=[
                    ColumnInfo(name="id", data_type="integer"),
                    ColumnInfo(name="col1", data_type="integer"),
                ],
            ),
            TableInfo(
                name="organization_units",
                columns=[
                    ColumnInfo(name="id", data_type="integer"),
                    ColumnInfo(name="province", data_type="character varying"),
                ],
            ),
        ],
        relationships=[],
    )


def test_validator_rejects_unquoted_national_id():
    validator = SQLValidator()
    intent = QueryIntent(requested_entity="employee", national_id="8223876400")

    result = validator.validate(
        "SELECT employees.first_name FROM employees WHERE employees.national_id = 8223876400",
        _schema(),
        intent=intent,
    )

    assert result.is_valid is False
    assert any("کد ملی" in error and "کوتیشن" in error for error in result.errors)


def test_validator_accepts_quoted_national_id():
    validator = SQLValidator()
    intent = QueryIntent(
        requested_entity="employee",
        national_id="8223876400",
        requested_columns=["first_name", "last_name", "national_id"],
    )

    result = validator.validate(
        "SELECT employees.first_name, employees.last_name, employees.national_id "
        "FROM employees WHERE employees.national_id = '8223876400'",
        _schema(),
        intent=intent,
    )

    assert result.is_valid is True


def test_validator_normalizes_persian_digits_in_table_and_column_names():
    validator = SQLValidator()

    result = validator.validate(
        "SELECT test۱.col۱ FROM test۱",
        _schema(),
    )

    assert result.is_valid is True


def test_validator_rejects_student_province_count_without_required_join_path():
    validator = SQLValidator()
    intent = QueryIntent(requested_entity="student", aggregation="COUNT", province="تهران")

    result = validator.validate(
        "SELECT COUNT(students.id) AS student_count FROM students",
        _schema(),
        intent=intent,
    )

    assert result.is_valid is False
    assert any("students -> schools -> organization_units" in error for error in result.errors)


def test_validator_rejects_school_count_that_counts_organization_units():
    validator = SQLValidator()
    intent = QueryIntent(requested_entity="school", aggregation="COUNT", province="تهران")

    result = validator.validate(
        "SELECT organization_units.province, COUNT(organization_units.id) AS school_count "
        "FROM organization_units WHERE organization_units.province = 'تهران' "
        "GROUP BY organization_units.province",
        _schema(),
        intent=intent,
    )

    assert result.is_valid is False
    assert any("schools.id" in error for error in result.errors)


def test_validator_rejects_count_intent_without_count():
    validator = SQLValidator()
    intent = QueryIntent(requested_entity="employee", aggregation="COUNT")

    result = validator.validate(
        "SELECT employees.first_name, employees.last_name FROM employees",
        _schema(),
        intent=intent,
    )

    assert result.is_valid is False
    assert any("COUNT" in error for error in result.errors)


def test_validator_rejects_employee_province_filter_on_unit_name():
    validator = SQLValidator()
    intent = QueryIntent(requested_entity="employee", province="تهران")

    result = validator.validate(
        "SELECT e.first_name, e.last_name FROM employees e "
        "JOIN organization_units ou ON e.organization_unit_id = ou.id "
        "WHERE ou.name = 'تهران'",
        _schema(),
        intent=intent,
    )

    assert result.is_valid is False
    assert any("organization_units.province" in error for error in result.errors)


def test_validator_rejects_select_star_for_safe_projection():
    validator = SQLValidator()

    result = validator.validate("SELECT * FROM employees", _schema())

    assert result.is_valid is False
    assert any("SELECT *" in error for error in result.errors)


def test_validator_rejects_limit_above_safe_cap():
    validator = SQLValidator()

    result = validator.validate("SELECT employees.id FROM employees LIMIT 5000", _schema())

    assert result.is_valid is False
    assert any("LIMIT" in error and "۱۰۰۰" in error for error in result.errors)


def test_validator_rejects_unfiltered_multi_join_list_without_limit():
    validator = SQLValidator()

    result = validator.validate(
        "SELECT students.id, schools.name, organization_units.province "
        "FROM students "
        "JOIN schools ON students.school_id = schools.id "
        "JOIN organization_units ON schools.organization_unit_id = organization_units.id",
        _schema(),
    )

    assert result.is_valid is False
    assert any("چندجدولی" in error for error in result.errors)


def test_validator_accepts_bounded_multi_join_list():
    validator = SQLValidator()

    result = validator.validate(
        "SELECT students.id, schools.name, organization_units.province "
        "FROM students "
        "JOIN schools ON students.school_id = schools.id "
        "JOIN organization_units ON schools.organization_unit_id = organization_units.id "
        "LIMIT 1000",
        _schema(),
    )

    assert result.is_valid is True


def test_validator_rejects_too_many_joins():
    schema = DatabaseSchema(
        tables=[
            TableInfo(name=f"t{i}", columns=[ColumnInfo(name="id", data_type="integer")])
            for i in range(6)
        ]
    )
    validator = SQLValidator()

    result = validator.validate(
        "SELECT t0.id FROM t0 "
        "JOIN t1 ON t0.id = t1.id "
        "JOIN t2 ON t1.id = t2.id "
        "JOIN t3 ON t2.id = t3.id "
        "JOIN t4 ON t3.id = t4.id "
        "JOIN t5 ON t4.id = t5.id "
        "LIMIT 1000",
        schema,
    )

    assert result.is_valid is False
    assert any("JOIN" in error for error in result.errors)
