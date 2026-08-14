from __future__ import annotations

from typing import Callable, Optional

from backend.semantic import semantic_catalog
from backend.sql.models import SQLPlan


TemplateFn = Callable[[SQLPlan], Optional[str]]


def sql_literal(value: object) -> str:
    text = "" if value is None else str(value)
    return "'" + text.replace("'", "''") + "'"


def filter_value(plan: SQLPlan, column: str, default: str = "") -> str:
    return next(
        (str(item.get("value")) for item in plan.filters if item.get("column") == column),
        default,
    )


def filter_values(plan: SQLPlan, column: str) -> list[str]:
    value = filter_value(plan, column)
    return [item for item in value.split("|") if item]


def province_group_where(plan: SQLPlan, table_name: str = "") -> str:
    values = filter_values(plan, "province_values")
    status = status_clause(plan, table_name) if table_name else ""
    if values:
        literals = ", ".join(sql_literal(value) for value in values)
        return f"WHERE organization_units.province IN ({literals}) {status}"
    return f"WHERE organization_units.province IS NOT NULL {status}"


def city_group_where(plan: SQLPlan, table_name: str = "") -> str:
    values = filter_values(plan, "city_values")
    status = status_clause(plan, table_name) if table_name else ""
    if values:
        literals = ", ".join(sql_literal(value) for value in values)
        return f"WHERE organization_units.city IN ({literals}) {status}"
    return f"WHERE organization_units.city IS NOT NULL {status}"


def status_clause(plan: SQLPlan, table_name: str, prefix: str = "AND") -> str:
    status = filter_value(plan, "status")
    return f"{prefix} {table_name}.status = {sql_literal(status)} " if status else ""


def person_name_clause(plan: SQLPlan, table_name: str, prefix: str = "AND") -> str:
    clauses = []
    first_name = filter_value(plan, "first_name")
    last_name = filter_value(plan, "last_name")
    if first_name:
        clauses.append(f"{table_name}.first_name = {sql_literal(first_name)}")
    if last_name:
        clauses.append(f"{table_name}.last_name = {sql_literal(last_name)}")
    return f"{prefix} " + " AND ".join(clauses) + " " if clauses else ""


def student_attribute_clause(plan: SQLPlan, prefix: str = "AND") -> str:
    clauses = []
    grade = filter_value(plan, "grade")
    enrollment_year = filter_value(plan, "enrollment_year")
    if grade:
        clauses.append(f"students.grade = {sql_literal(grade)}")
    if enrollment_year:
        clauses.append(f"students.enrollment_year = {int(enrollment_year)}")
    return f"{prefix} " + " AND ".join(clauses) + " " if clauses else ""


def employee_attribute_clause(plan: SQLPlan, prefix: str = "AND") -> str:
    clauses = []
    position = filter_value(plan, "position")
    hire_year = filter_value(plan, "hire_year")
    if position:
        clauses.append(f"employees.position = {sql_literal(position)}")
    if hire_year:
        clauses.append(f"EXTRACT(YEAR FROM employees.hire_date) = {int(hire_year)}")
    return f"{prefix} " + " AND ".join(clauses) + " " if clauses else ""


def school_attribute_clause(plan: SQLPlan, prefix: str = "AND") -> str:
    clauses = []
    school_type = filter_value(plan, "school_type")
    capacity_min = filter_value(plan, "capacity_min")
    established_year = filter_value(plan, "established_year")
    if school_type:
        clauses.append(f"schools.school_type = {sql_literal(school_type)}")
    if capacity_min:
        clauses.append(f"schools.capacity >= {int(capacity_min)}")
    if established_year:
        clauses.append(f"schools.established_year = {int(established_year)}")
    return f"{prefix} " + " AND ".join(clauses) + " " if clauses else ""


def salary_time_where_clause(plan: SQLPlan) -> str:
    clauses = []
    year = filter_value(plan, "year")
    month = filter_value(plan, "month")
    if year:
        clauses.append(f"salary_items.year = {int(year)}")
    if month:
        clauses.append(f"salary_items.month = {int(month)}")
    return " WHERE " + " AND ".join(clauses) + " " if clauses else ""


def salary_where_clause(plan: SQLPlan) -> str:
    clauses = []
    year = filter_value(plan, "year")
    month = filter_value(plan, "month")
    if year:
        clauses.append(f"salary_items.year = {int(year)}")
    if month:
        clauses.append(f"salary_items.month = {int(month)}")
    national_id = filter_value(plan, "national_id")
    if national_id:
        clauses.append(f"employees.national_id = {sql_literal(national_id)}")
    first_name = filter_value(plan, "first_name")
    if first_name:
        clauses.append(f"employees.first_name = {sql_literal(first_name)}")
    last_name = filter_value(plan, "last_name")
    if last_name:
        clauses.append(f"employees.last_name = {sql_literal(last_name)}")
    status = filter_value(plan, "status")
    if status:
        clauses.append(f"employees.status = {sql_literal(status)}")
    position = filter_value(plan, "position")
    if position:
        clauses.append(f"employees.position = {sql_literal(position)}")
    hire_year = filter_value(plan, "hire_year")
    if hire_year:
        clauses.append(f"EXTRACT(YEAR FROM employees.hire_date) = {int(hire_year)}")
    province = filter_value(plan, "province")
    if province:
        clauses.append(f"organization_units.province = {sql_literal(province)}")
    city = filter_value(plan, "city")
    if city:
        clauses.append(f"organization_units.city = {sql_literal(city)}")
    return " WHERE " + " AND ".join(clauses) + " " if clauses else " "


def salary_joins(plan: SQLPlan) -> str:
    joins = "JOIN employees ON salary_items.employee_id = employees.id "
    if "organization_units" in set(plan.required_tables):
        joins += "JOIN organization_units ON employees.organization_unit_id = organization_units.id "
    return joins


def ranking_direction(plan: SQLPlan, default: str = "DESC") -> str:
    return "ASC" if plan.order_by and "ASC" in plan.order_by.upper() else default


def limit_clause(plan: SQLPlan) -> str:
    return f" LIMIT {plan.limit}" if plan.limit else ""


def _selected(plan: SQLPlan) -> set[str]:
    return set(plan.selected_columns)


def _projection(table_name: str, requested_columns: list[str]) -> str:
    table = semantic_catalog.table(table_name)
    allowed = {column.name for column in table.columns} if table else set()
    pii_columns = {column.name for column in table.columns if column.pii} if table else set()
    qualified_columns = []
    columns = []
    for column in requested_columns:
        if "." in column:
            target_table, target_column = column.split(".", 1)
            if target_column in _generic_table_columns(target_table):
                qualified_columns.append(f"{target_table}.{target_column}")
        elif column in allowed:
            columns.append(column)
    if not columns and not qualified_columns and table:
        columns = [column for column in table.default_display_columns if column not in pii_columns]
    return ", ".join([f"{table_name}.{column}" for column in columns] + qualified_columns)


def _generic_table_columns(table_name: str) -> set[str]:
    table = semantic_catalog.table(table_name)
    return {column.name for column in table.columns} if table else set()


def _generic_filter_target(column: str, base_table: str, required_tables: set[str]) -> tuple[str, str] | None:
    if "." in column:
        table_name, column_name = column.split(".", 1)
        if table_name in required_tables and column_name in _generic_table_columns(table_name):
            return table_name, column_name
        return None
    if column in _generic_table_columns(base_table):
        return base_table, column
    matches = [
        table_name
        for table_name in required_tables
        if table_name != base_table and column in _generic_table_columns(table_name)
    ]
    if len(matches) == 1:
        return matches[0], column
    return None


def _generic_from_join_clause(plan: SQLPlan, base_table: str) -> str:
    clause = f"FROM {base_table}"
    joined = {base_table}
    pending = list(plan.joins)
    while pending:
        progressed = False
        remaining = []
        for join in pending:
            from_table = join.get("from_table", "")
            to_table = join.get("to_table", "")
            from_column = join.get("from_column", "")
            to_column = join.get("to_column", "")
            if from_table in joined and to_table not in joined:
                clause += f" JOIN {to_table} ON {from_table}.{from_column} = {to_table}.{to_column}"
                joined.add(to_table)
                progressed = True
            elif to_table in joined and from_table not in joined:
                clause += f" JOIN {from_table} ON {from_table}.{from_column} = {to_table}.{to_column}"
                joined.add(from_table)
                progressed = True
            else:
                remaining.append(join)
        if not progressed:
            break
        pending = remaining
    return clause


def _generic_column_sql(column: str, base_table: str, required_tables: set[str]) -> str | None:
    target = _generic_filter_target(column, base_table, required_tables)
    if not target:
        return None
    table_name, column_name = target
    return f"{table_name}.{column_name}"


def generic_table_count(plan: SQLPlan) -> Optional[str]:
    if "GENERIC_TABLE_COUNT" not in _selected(plan):
        return None
    table_name = plan.required_tables[0]
    table = semantic_catalog.table(table_name)
    if not table:
        return None
    count_column = table.primary_key or "id"
    required_tables = set(plan.required_tables)
    group_columns = [
        column_sql
        for column in plan.group_by
        if (column_sql := _generic_column_sql(column, table_name, required_tables))
    ]
    if group_columns:
        projection = ", ".join(group_columns)
        group_by = ", ".join(group_columns)
        return (
            f"SELECT {projection}, COUNT({table_name}.{count_column}) AS row_count "
            f"{_generic_from_join_clause(plan, table_name)}"
            f"{generic_filter_where(plan, table_name)} "
            f"GROUP BY {group_by} ORDER BY {group_by}"
        )
    return (
        f"SELECT COUNT({table_name}.{count_column}) AS row_count "
        f"{_generic_from_join_clause(plan, table_name)}"
        f"{generic_filter_where(plan, table_name)}"
    )


def generic_table_list(plan: SQLPlan) -> Optional[str]:
    if "GENERIC_TABLE_LIST" not in _selected(plan):
        return None
    table_name = plan.required_tables[0]
    table = semantic_catalog.table(table_name)
    if not table:
        return None
    requested_columns = [
        column for column in plan.selected_columns if column != "GENERIC_TABLE_LIST"
    ]
    projection = _projection(table_name, requested_columns)
    if not projection:
        projection = f"{table_name}.{table.primary_key or 'id'}"
    order_by = f"{table_name}.{table.primary_key or 'id'}"
    if plan.order_by:
        column, _, direction = plan.order_by.partition(" ")
        column_sql = _generic_column_sql(column, table_name, set(plan.required_tables))
        if column_sql and direction.upper() in {"ASC", "DESC"}:
            order_by = f"{column_sql} {direction.upper()}"
    limit = f" LIMIT {plan.limit or 1000}"
    return (
        f"SELECT {projection} "
        f"{_generic_from_join_clause(plan, table_name)}"
        f"{generic_filter_where(plan, table_name)} "
        f"ORDER BY {order_by}{limit}"
    )


def generic_table_aggregate(plan: SQLPlan) -> Optional[str]:
    if "GENERIC_TABLE_AGGREGATE" not in _selected(plan):
        return None
    if not plan.aggregations:
        return None
    table_name = plan.required_tables[0]
    table = semantic_catalog.table(table_name)
    if not table:
        return None
    required_tables = set(plan.required_tables)
    aggregation = plan.aggregations[0]
    function = aggregation.get("function", "").upper()
    if function not in {"AVG", "SUM", "MIN", "MAX"}:
        return None
    column_sql = _generic_column_sql(aggregation.get("column", ""), table_name, required_tables)
    if not column_sql:
        return None
    output_name = f"{function.lower()}_{column_sql.split('.')[-1]}"
    group_columns = [
        group_sql
        for column in plan.group_by
        if (group_sql := _generic_column_sql(column, table_name, required_tables))
    ]
    if group_columns:
        projection = ", ".join(group_columns)
        group_by = ", ".join(group_columns)
        return (
            f"SELECT {projection}, {function}({column_sql}) AS {output_name} "
            f"{_generic_from_join_clause(plan, table_name)}"
            f"{generic_filter_where(plan, table_name)} "
            f"GROUP BY {group_by} ORDER BY {group_by}"
        )
    return (
        f"SELECT {function}({column_sql}) AS {output_name} "
        f"{_generic_from_join_clause(plan, table_name)}"
        f"{generic_filter_where(plan, table_name)}"
    )


def generic_filter_where(plan: SQLPlan, table_name: str) -> str:
    required_tables = set(plan.required_tables)
    clauses = []
    for item in plan.filters:
        column = item.get("column", "")
        operator = item.get("operator", "=")
        value = item.get("value", "")
        target = _generic_filter_target(column, table_name, required_tables)
        if not target or (value == "" and operator not in {"YEAR_CURRENT", "PREVIOUS_MONTH"}):
            continue
        target_table, target_column = target
        if operator in {">", "<", ">=", "<="}:
            clauses.append(f"{target_table}.{target_column} {operator} {int(value)}")
        elif operator == "YEAR=":
            clauses.append(f"EXTRACT(YEAR FROM {target_table}.{target_column}) = {int(value)}")
        elif operator == "MONTH=":
            clauses.append(f"EXTRACT(MONTH FROM {target_table}.{target_column}) = {int(value)}")
        elif operator == "YEAR_CURRENT":
            clauses.append(f"EXTRACT(YEAR FROM {target_table}.{target_column}) = EXTRACT(YEAR FROM CURRENT_DATE)")
        elif operator == "PREVIOUS_MONTH":
            clauses.append(
                f"{target_table}.{target_column} >= date_trunc('month', CURRENT_DATE - INTERVAL '1 month') "
                f"AND {target_table}.{target_column} < date_trunc('month', CURRENT_DATE)"
            )
        elif operator == "DAYS_AGO":
            clauses.append(f"{target_table}.{target_column} >= CURRENT_DATE - INTERVAL '{int(value)} days'")
        elif operator == "DATE=" and value == "CURRENT_DATE":
            clauses.append(f"{target_table}.{target_column}::date = CURRENT_DATE")
        else:
            clauses.append(f"{target_table}.{target_column} = {sql_literal(value)}")
    return " WHERE " + " AND ".join(clauses) if clauses else ""


def training_request_where_clause(plan: SQLPlan) -> str:
    clauses = []
    table = semantic_catalog.table("demo_training_requests")
    allowed_columns = {column.name for column in table.columns} if table else set()
    for item in plan.filters:
        column = item.get("column", "")
        value = item.get("value", "")
        operator = item.get("operator", "=")
        if column == "estimated_cost_min" or column not in allowed_columns or value == "":
            continue
        if operator in {">", "<", ">=", "<="}:
            clauses.append(f"demo_training_requests.{column} {operator} {int(value)}")
        else:
            clauses.append(f"demo_training_requests.{column} = {sql_literal(value)}")
    cost_min = filter_value(plan, "estimated_cost_min")
    if cost_min:
        clauses.append(f"demo_training_requests.estimated_cost > {int(cost_min)}")
    return " WHERE " + " AND ".join(clauses) if clauses else ""


def training_request_count(plan: SQLPlan) -> Optional[str]:
    if set(plan.required_tables) != {"demo_training_requests"}:
        return None
    if "TRAINING_REQUEST_COUNT" not in _selected(plan):
        return None
    return (
        "SELECT COUNT(demo_training_requests.id) AS training_request_count "
        "FROM demo_training_requests"
        f"{training_request_where_clause(plan)}"
    )


def training_request_list(plan: SQLPlan) -> Optional[str]:
    if set(plan.required_tables) != {"demo_training_requests"}:
        return None
    if "TRAINING_REQUEST_LIST" not in _selected(plan):
        return None
    requested_columns = [
        column for column in plan.selected_columns if column != "TRAINING_REQUEST_LIST"
    ]
    projection = _projection("demo_training_requests", requested_columns)
    return (
        f"SELECT {projection} "
        "FROM demo_training_requests"
        f"{training_request_where_clause(plan)} "
        "ORDER BY demo_training_requests.requested_at DESC, demo_training_requests.id"
    )


def training_request_cost_sum(plan: SQLPlan) -> Optional[str]:
    if set(plan.required_tables) != {"demo_training_requests"}:
        return None
    if "TRAINING_REQUEST_COST_SUM" not in _selected(plan):
        return None
    return (
        "SELECT SUM(demo_training_requests.estimated_cost) AS total_estimated_cost "
        "FROM demo_training_requests"
        f"{training_request_where_clause(plan)}"
    )


def training_request_cost_avg(plan: SQLPlan) -> Optional[str]:
    if set(plan.required_tables) != {"demo_training_requests"}:
        return None
    if "TRAINING_REQUEST_COST_AVG" not in _selected(plan):
        return None
    return (
        "SELECT AVG(demo_training_requests.estimated_cost) AS avg_estimated_cost "
        "FROM demo_training_requests"
        f"{training_request_where_clause(plan)}"
    )


def training_request_ranked_cost(plan: SQLPlan) -> Optional[str]:
    if set(plan.required_tables) != {"demo_training_requests"} or plan.limit != 1:
        return None
    if "TRAINING_REQUEST_RANKED_COST" not in _selected(plan):
        return None
    direction = "ASC" if plan.order_by and "ASC" in plan.order_by.upper() else "DESC"
    return (
        "SELECT demo_training_requests.requester_name, demo_training_requests.request_type, "
        "demo_training_requests.province, demo_training_requests.status, "
        "demo_training_requests.estimated_cost "
        "FROM demo_training_requests"
        f"{training_request_where_clause(plan)} "
        f"ORDER BY demo_training_requests.estimated_cost {direction} "
        "LIMIT 1"
    )


def composable_counts_by_province(plan: SQLPlan) -> Optional[str]:
    if "COMPOSABLE_COUNTS_BY_PROVINCE" not in _selected(plan):
        return None
    province = filter_value(plan, "province")
    outer_where = f"WHERE ou.province = {sql_literal(province)} " if province else "WHERE ou.province IS NOT NULL "
    if "COMPOSABLE_SCHOOL_STUDENT" in _selected(plan):
        return (
            "SELECT ou.province, "
            "(SELECT COUNT(DISTINCT sc.id) FROM schools sc "
            "JOIN organization_units su ON sc.organization_unit_id = su.id "
            "WHERE su.province = ou.province) AS school_count, "
            "(SELECT COUNT(st.id) FROM students st "
            "JOIN schools ss ON st.school_id = ss.id "
            "JOIN organization_units stu ON ss.organization_unit_id = stu.id "
            "WHERE stu.province = ou.province) AS student_count "
            "FROM organization_units ou "
            f"{outer_where}"
            "GROUP BY ou.province "
            "ORDER BY ou.province"
        )
    return (
        "SELECT ou.province, "
        "(SELECT COUNT(e.id) FROM employees e "
        "JOIN organization_units eu ON e.organization_unit_id = eu.id "
        "WHERE eu.province = ou.province) AS employee_count, "
        "(SELECT COUNT(st.id) FROM students st "
        "JOIN schools sc ON st.school_id = sc.id "
        "JOIN organization_units su ON sc.organization_unit_id = su.id "
        "WHERE su.province = ou.province) AS student_count "
        "FROM organization_units ou "
        f"{outer_where}"
        "GROUP BY ou.province "
        "ORDER BY ou.province"
    )


def composable_counts_by_city(plan: SQLPlan) -> Optional[str]:
    if "COMPOSABLE_COUNTS_BY_CITY" not in _selected(plan):
        return None
    city = filter_value(plan, "city")
    outer_where = f"WHERE ou.city = {sql_literal(city)} " if city else "WHERE ou.city IS NOT NULL "
    if "COMPOSABLE_EMPLOYEE_STUDENT" in _selected(plan):
        return (
            "SELECT ou.city AS region, "
            "(SELECT COUNT(e.id) FROM employees e "
            "JOIN organization_units eu ON e.organization_unit_id = eu.id "
            "WHERE eu.city = ou.city) AS employee_count, "
            "(SELECT COUNT(st.id) FROM students st "
            "JOIN schools ss ON st.school_id = ss.id "
            "JOIN organization_units stu ON ss.organization_unit_id = stu.id "
            "WHERE stu.city = ou.city) AS student_count "
            "FROM organization_units ou "
            f"{outer_where}"
            "GROUP BY ou.city "
            "ORDER BY ou.city"
        )
    return (
        "SELECT ou.city AS region, "
        "(SELECT COUNT(sc.id) FROM schools sc "
        "JOIN organization_units su ON sc.organization_unit_id = su.id "
        "WHERE su.city = ou.city) AS school_count, "
        "(SELECT COUNT(st.id) FROM students st "
        "JOIN schools ss ON st.school_id = ss.id "
        "JOIN organization_units stu ON ss.organization_unit_id = stu.id "
        "WHERE stu.city = ou.city) AS student_count "
        "FROM organization_units ou "
        f"{outer_where}"
        "GROUP BY ou.city "
        "ORDER BY ou.city"
    )


def student_total_count(plan: SQLPlan) -> Optional[str]:
    if set(plan.required_tables) == {"students"} and any("COUNT" in column.upper() for column in plan.selected_columns):
        clauses = []
        status = filter_value(plan, "status")
        grade = filter_value(plan, "grade")
        enrollment_year = filter_value(plan, "enrollment_year")
        if status:
            clauses.append(f"students.status = {sql_literal(status)}")
        if grade:
            clauses.append(f"students.grade = {sql_literal(grade)}")
        if enrollment_year:
            clauses.append(f"students.enrollment_year = {int(enrollment_year)}")
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        return f"SELECT COUNT(students.id) AS total_students FROM students{where}"
    return None


def student_count_grouped_by_province(plan: SQLPlan) -> Optional[str]:
    if set(plan.required_tables) != {"students", "schools", "organization_units"}:
        return None
    if "STUDENT_COUNT_GROUPED_BY_PROVINCE" not in _selected(plan):
        return None
    direction = ranking_direction(plan)
    return (
        "SELECT organization_units.province, COUNT(students.id) AS student_count "
        "FROM students "
        "JOIN schools ON students.school_id = schools.id "
        "JOIN organization_units ON schools.organization_unit_id = organization_units.id "
        f"{province_group_where(plan, 'students')}"
        "GROUP BY organization_units.province "
        f"ORDER BY student_count {direction}"
        f"{limit_clause(plan)}"
    )


def student_count_grouped_by_city(plan: SQLPlan) -> Optional[str]:
    if set(plan.required_tables) != {"students", "schools", "organization_units"}:
        return None
    if "STUDENT_COUNT_GROUPED_BY_CITY" not in _selected(plan):
        return None
    direction = ranking_direction(plan)
    return (
        "SELECT organization_units.city, COUNT(students.id) AS student_count "
        "FROM students "
        "JOIN schools ON students.school_id = schools.id "
        "JOIN organization_units ON schools.organization_unit_id = organization_units.id "
        f"{city_group_where(plan, 'students')}"
        "GROUP BY organization_units.city "
        f"ORDER BY student_count {direction}"
        f"{limit_clause(plan)}"
    )


def student_list_by_status(plan: SQLPlan) -> Optional[str]:
    if set(plan.required_tables) != {"students"}:
        return None
    if "STUDENT_LIST_BY_STATUS" not in _selected(plan):
        return None
    status = filter_value(plan, "status")
    attr_filter = student_attribute_clause(plan)
    return (
        "SELECT students.id, students.first_name, students.last_name, students.national_id, "
        "students.grade, students.status, students.school_id "
        "FROM students "
        f"WHERE students.status = {sql_literal(status)} "
        f"{attr_filter}"
        "ORDER BY students.id"
    )


def student_by_national_id(plan: SQLPlan) -> Optional[str]:
    if set(plan.required_tables) != {"students"}:
        return None
    if "STUDENT_BY_NATIONAL_ID" not in _selected(plan):
        return None
    national_id = filter_value(plan, "national_id")
    requested_columns = [
        column for column in plan.selected_columns if column != "STUDENT_BY_NATIONAL_ID"
    ]
    projection = _projection("students", requested_columns)
    return (
        f"SELECT {projection} "
        "FROM students "
        f"WHERE students.national_id = {sql_literal(national_id)}"
    )


def student_count_by_name(plan: SQLPlan) -> Optional[str]:
    if set(plan.required_tables) != {"students"}:
        return None
    if "STUDENT_COUNT_BY_NAME" not in _selected(plan):
        return None
    where = person_name_clause(plan, "students", prefix="WHERE")
    attr_filter = student_attribute_clause(plan)
    return (
        "SELECT COUNT(students.id) AS student_count "
        "FROM students "
        f"{where}"
        f"{attr_filter}"
    )


def student_list_by_name(plan: SQLPlan) -> Optional[str]:
    if set(plan.required_tables) != {"students"}:
        return None
    if "STUDENT_LIST_BY_NAME" not in _selected(plan):
        return None
    requested_columns = [
        column for column in plan.selected_columns if column != "STUDENT_LIST_BY_NAME"
    ]
    projection = _projection("students", requested_columns)
    where = person_name_clause(plan, "students", prefix="WHERE")
    attr_filter = student_attribute_clause(plan)
    return (
        f"SELECT {projection} "
        "FROM students "
        f"{where}"
        f"{attr_filter}"
        "ORDER BY students.last_name, students.first_name, students.id"
    )


def student_school_name_by_name(plan: SQLPlan) -> Optional[str]:
    if set(plan.required_tables) != {"students", "schools"}:
        return None
    if "STUDENT_SCHOOL_NAME_BY_NAME" not in _selected(plan):
        return None
    name_filter = person_name_clause(plan, "students")
    attr_filter = student_attribute_clause(plan)
    return (
        "SELECT students.first_name, students.last_name, students.grade, schools.name AS school_name "
        "FROM students "
        "JOIN schools ON students.school_id = schools.id "
        "WHERE 1 = 1 "
        f"{name_filter}"
        f"{attr_filter}"
        "ORDER BY students.last_name, students.first_name, students.id"
    )


def student_count_by_province(plan: SQLPlan) -> Optional[str]:
    if set(plan.required_tables) != {"students", "schools", "organization_units"}:
        return None
    if "STUDENT_COUNT_BY_PROVINCE" not in _selected(plan):
        return None
    province = filter_value(plan, "province")
    name_filter = person_name_clause(plan, "students")
    status_filter = status_clause(plan, "students")
    attr_filter = student_attribute_clause(plan)
    return (
        "SELECT organization_units.province, COUNT(students.id) AS student_count "
        "FROM students "
        "JOIN schools ON students.school_id = schools.id "
        "JOIN organization_units ON schools.organization_unit_id = organization_units.id "
        f"WHERE organization_units.province = {sql_literal(province)} "
        f"{name_filter}"
        f"{status_filter}"
        f"{attr_filter}"
        "GROUP BY organization_units.province"
    )


def student_list_by_province(plan: SQLPlan) -> Optional[str]:
    if set(plan.required_tables) != {"students", "schools", "organization_units"}:
        return None
    if "STUDENT_LIST_BY_PROVINCE" not in _selected(plan):
        return None
    province = filter_value(plan, "province")
    name_filter = person_name_clause(plan, "students")
    status_filter = status_clause(plan, "students")
    attr_filter = student_attribute_clause(plan)
    return (
        "SELECT students.id, students.first_name, students.last_name, students.national_id, "
        "students.grade, students.status, schools.name AS school_name, "
        "organization_units.province, organization_units.city "
        "FROM students "
        "JOIN schools ON students.school_id = schools.id "
        "JOIN organization_units ON schools.organization_unit_id = organization_units.id "
        f"WHERE organization_units.province = {sql_literal(province)} "
        f"{name_filter}"
        f"{status_filter}"
        f"{attr_filter}"
        "ORDER BY students.id"
    )


def student_count_by_city(plan: SQLPlan) -> Optional[str]:
    if set(plan.required_tables) != {"students", "schools", "organization_units"}:
        return None
    if "STUDENT_COUNT_BY_CITY" not in _selected(plan):
        return None
    city = filter_value(plan, "city")
    name_filter = person_name_clause(plan, "students")
    status_filter = status_clause(plan, "students")
    attr_filter = student_attribute_clause(plan)
    return (
        "SELECT organization_units.city, COUNT(students.id) AS student_count "
        "FROM students "
        "JOIN schools ON students.school_id = schools.id "
        "JOIN organization_units ON schools.organization_unit_id = organization_units.id "
        f"WHERE organization_units.city = {sql_literal(city)} "
        f"{name_filter}"
        f"{status_filter}"
        f"{attr_filter}"
        "GROUP BY organization_units.city"
    )


def student_list_by_city(plan: SQLPlan) -> Optional[str]:
    if set(plan.required_tables) != {"students", "schools", "organization_units"}:
        return None
    if "STUDENT_LIST_BY_CITY" not in _selected(plan):
        return None
    city = filter_value(plan, "city")
    name_filter = person_name_clause(plan, "students")
    status_filter = status_clause(plan, "students")
    attr_filter = student_attribute_clause(plan)
    return (
        "SELECT students.id, students.first_name, students.last_name, students.national_id, "
        "students.grade, students.status, schools.name AS school_name, "
        "organization_units.province, organization_units.city "
        "FROM students "
        "JOIN schools ON students.school_id = schools.id "
        "JOIN organization_units ON schools.organization_unit_id = organization_units.id "
        f"WHERE organization_units.city = {sql_literal(city)} "
        f"{name_filter}"
        f"{status_filter}"
        f"{attr_filter}"
        "ORDER BY students.id"
    )


def student_list_by_school_name(plan: SQLPlan) -> Optional[str]:
    if set(plan.required_tables) != {"students", "schools"}:
        return None
    if "STUDENT_LIST_BY_SCHOOL_NAME" not in _selected(plan):
        return None
    school_name = filter_value(plan, "school_name")
    status_filter = status_clause(plan, "students")
    name_filter = person_name_clause(plan, "students")
    attr_filter = student_attribute_clause(plan)
    return (
        "SELECT students.id, students.first_name, students.last_name, students.national_id, "
        "students.grade, students.status, schools.name AS school_name "
        "FROM students "
        "JOIN schools ON students.school_id = schools.id "
        f"WHERE schools.name = {sql_literal(school_name)} "
        f"{status_filter}"
        f"{name_filter}"
        f"{attr_filter}"
        "ORDER BY students.id"
    )


def student_count_by_school_name(plan: SQLPlan) -> Optional[str]:
    if set(plan.required_tables) != {"students", "schools"}:
        return None
    if "STUDENT_COUNT_BY_SCHOOL_NAME" not in _selected(plan):
        return None
    school_name = filter_value(plan, "school_name")
    status_filter = status_clause(plan, "students")
    name_filter = person_name_clause(plan, "students")
    attr_filter = student_attribute_clause(plan)
    return (
        "SELECT schools.name AS school_name, COUNT(students.id) AS student_count "
        "FROM students "
        "JOIN schools ON students.school_id = schools.id "
        f"WHERE schools.name = {sql_literal(school_name)} "
        f"{status_filter}"
        f"{name_filter}"
        f"{attr_filter}"
        "GROUP BY schools.name"
    )


def school_names_by_province(plan: SQLPlan) -> Optional[str]:
    if set(plan.required_tables) != {"schools", "organization_units"}:
        return None
    if "SCHOOL_NAMES_BY_PROVINCE" not in _selected(plan):
        return None
    province = filter_value(plan, "province")
    attr_filter = school_attribute_clause(plan)
    return (
        "SELECT schools.id, schools.name, schools.school_type, organization_units.province, organization_units.city "
        "FROM schools "
        "JOIN organization_units ON schools.organization_unit_id = organization_units.id "
        f"WHERE organization_units.province = {sql_literal(province)} "
        f"{attr_filter}"
        "ORDER BY schools.name, schools.id"
    )


def school_count_by_province(plan: SQLPlan) -> Optional[str]:
    if set(plan.required_tables) != {"schools", "organization_units"}:
        return None
    if "SCHOOL_COUNT_BY_PROVINCE" not in _selected(plan):
        return None
    province = filter_value(plan, "province")
    attr_filter = school_attribute_clause(plan)
    return (
        "SELECT organization_units.province, COUNT(DISTINCT schools.id) AS school_count "
        "FROM schools "
        "JOIN organization_units ON schools.organization_unit_id = organization_units.id "
        f"WHERE organization_units.province = {sql_literal(province)} "
        f"{attr_filter}"
        "GROUP BY organization_units.province"
    )


def school_names_by_city(plan: SQLPlan) -> Optional[str]:
    if set(plan.required_tables) != {"schools", "organization_units"}:
        return None
    if "SCHOOL_NAMES_BY_CITY" not in _selected(plan):
        return None
    city = filter_value(plan, "city")
    attr_filter = school_attribute_clause(plan)
    return (
        "SELECT schools.id, schools.name, schools.school_type, organization_units.province, organization_units.city "
        "FROM schools "
        "JOIN organization_units ON schools.organization_unit_id = organization_units.id "
        f"WHERE organization_units.city = {sql_literal(city)} "
        f"{attr_filter}"
        "ORDER BY schools.name, schools.id"
    )


def school_count_by_city(plan: SQLPlan) -> Optional[str]:
    if set(plan.required_tables) != {"schools", "organization_units"}:
        return None
    if "SCHOOL_COUNT_BY_CITY" not in _selected(plan):
        return None
    city = filter_value(plan, "city")
    attr_filter = school_attribute_clause(plan)
    return (
        "SELECT organization_units.city, COUNT(DISTINCT schools.id) AS school_count "
        "FROM schools "
        "JOIN organization_units ON schools.organization_unit_id = organization_units.id "
        f"WHERE organization_units.city = {sql_literal(city)} "
        f"{attr_filter}"
        "GROUP BY organization_units.city"
    )


def school_count_grouped_by_province(plan: SQLPlan) -> Optional[str]:
    if set(plan.required_tables) != {"schools", "organization_units"}:
        return None
    if "SCHOOL_COUNT_GROUPED_BY_PROVINCE" not in _selected(plan):
        return None
    direction = ranking_direction(plan)
    return (
        "SELECT organization_units.province, COUNT(DISTINCT schools.id) AS school_count "
        "FROM schools "
        "JOIN organization_units ON schools.organization_unit_id = organization_units.id "
        f"{province_group_where(plan)}"
        f"{school_attribute_clause(plan)}"
        "GROUP BY organization_units.province "
        f"ORDER BY school_count {direction}"
        f"{limit_clause(plan)}"
    )


def school_count_grouped_by_city(plan: SQLPlan) -> Optional[str]:
    if set(plan.required_tables) != {"schools", "organization_units"}:
        return None
    if "SCHOOL_COUNT_GROUPED_BY_CITY" not in _selected(plan):
        return None
    direction = ranking_direction(plan)
    return (
        "SELECT organization_units.city, COUNT(DISTINCT schools.id) AS school_count "
        "FROM schools "
        "JOIN organization_units ON schools.organization_unit_id = organization_units.id "
        f"{city_group_where(plan)}"
        f"{school_attribute_clause(plan)}"
        "GROUP BY organization_units.city "
        f"ORDER BY school_count {direction}"
        f"{limit_clause(plan)}"
    )


def school_names_by_org_unit_name(plan: SQLPlan) -> Optional[str]:
    if set(plan.required_tables) != {"schools", "organization_units"}:
        return None
    if "SCHOOL_NAMES_BY_ORG_UNIT_NAME" not in _selected(plan):
        return None
    unit_name = filter_value(plan, "organization_unit_name")
    attr_filter = school_attribute_clause(plan)
    return (
        "SELECT schools.id, schools.name, schools.school_type, organization_units.name AS organization_unit_name, "
        "organization_units.province, organization_units.city "
        "FROM schools "
        "JOIN organization_units ON schools.organization_unit_id = organization_units.id "
        f"WHERE organization_units.name = {sql_literal(unit_name)} "
        f"{attr_filter}"
        "ORDER BY schools.name, schools.id"
    )


def school_count_by_org_unit_name(plan: SQLPlan) -> Optional[str]:
    if set(plan.required_tables) != {"schools", "organization_units"}:
        return None
    if "SCHOOL_COUNT_BY_ORG_UNIT_NAME" not in _selected(plan):
        return None
    unit_name = filter_value(plan, "organization_unit_name")
    attr_filter = school_attribute_clause(plan)
    return (
        "SELECT organization_units.name AS organization_unit_name, COUNT(DISTINCT schools.id) AS school_count "
        "FROM schools "
        "JOIN organization_units ON schools.organization_unit_id = organization_units.id "
        f"WHERE organization_units.name = {sql_literal(unit_name)} "
        f"{attr_filter}"
        "GROUP BY organization_units.name"
    )


def school_phone_by_name(plan: SQLPlan) -> Optional[str]:
    if set(plan.required_tables) != {"schools"}:
        return None
    if "SCHOOL_PHONE_BY_NAME" not in _selected(plan):
        return None
    school_name = filter_value(plan, "name")
    return (
        "SELECT schools.name, schools.phone "
        "FROM schools "
        f"WHERE schools.name = {sql_literal(school_name)} "
        "ORDER BY schools.name"
    )


def organization_unit_by_name(plan: SQLPlan) -> Optional[str]:
    if set(plan.required_tables) != {"organization_units"}:
        return None
    if "ORGANIZATION_UNIT_BY_NAME" not in _selected(plan):
        return None
    unit_name = filter_value(plan, "name")
    return (
        "SELECT organization_units.id, organization_units.name, organization_units.unit_type, "
        "organization_units.parent_id, organization_units.province, organization_units.city, organization_units.created_at "
        "FROM organization_units "
        f"WHERE organization_units.name = {sql_literal(unit_name)} "
        "ORDER BY organization_units.id"
    )


def school_by_name(plan: SQLPlan) -> Optional[str]:
    if set(plan.required_tables) != {"schools"}:
        return None
    if "SCHOOL_BY_NAME" not in _selected(plan):
        return None
    school_name = filter_value(plan, "name")
    attr_filter = school_attribute_clause(plan)
    requested_columns = [
        column for column in plan.selected_columns if column != "SCHOOL_BY_NAME"
    ]
    projection = _projection("schools", requested_columns)
    return (
        f"SELECT {projection} "
        "FROM schools "
        f"WHERE schools.name = {sql_literal(school_name)} "
        f"{attr_filter}"
        "ORDER BY schools.id"
    )


def school_count_filtered(plan: SQLPlan) -> Optional[str]:
    if set(plan.required_tables) != {"schools"}:
        return None
    if "SCHOOL_COUNT_FILTERED" not in _selected(plan):
        return None
    attr_filter = school_attribute_clause(plan, prefix="WHERE")
    return (
        "SELECT COUNT(DISTINCT schools.id) AS school_count "
        "FROM schools "
        f"{attr_filter}"
    )


def school_list_filtered(plan: SQLPlan) -> Optional[str]:
    if set(plan.required_tables) != {"schools"}:
        return None
    if "SCHOOL_LIST_FILTERED" not in _selected(plan):
        return None
    requested_columns = [
        column for column in plan.selected_columns if column != "SCHOOL_LIST_FILTERED"
    ]
    projection = _projection("schools", requested_columns)
    attr_filter = school_attribute_clause(plan, prefix="WHERE")
    return (
        f"SELECT {projection} "
        "FROM schools "
        f"{attr_filter}"
        "ORDER BY schools.name, schools.id"
    )


def employee_count_by_province(plan: SQLPlan) -> Optional[str]:
    if set(plan.required_tables) != {"employees", "organization_units"}:
        return None
    if "EMPLOYEE_COUNT_BY_PROVINCE" not in _selected(plan):
        return None
    province = filter_value(plan, "province")
    status_filter = status_clause(plan, "employees")
    name_filter = person_name_clause(plan, "employees")
    attr_filter = employee_attribute_clause(plan)
    return (
        "SELECT organization_units.province, COUNT(employees.id) AS employee_count "
        "FROM employees "
        "JOIN organization_units ON employees.organization_unit_id = organization_units.id "
        f"WHERE organization_units.province = {sql_literal(province)} "
        f"{status_filter}"
        f"{name_filter}"
        f"{attr_filter}"
        "GROUP BY organization_units.province"
    )


def employee_count_grouped_by_province(plan: SQLPlan) -> Optional[str]:
    if set(plan.required_tables) != {"employees", "organization_units"}:
        return None
    if "EMPLOYEE_COUNT_GROUPED_BY_PROVINCE" not in _selected(plan):
        return None
    direction = ranking_direction(plan)
    return (
        "SELECT organization_units.province, COUNT(employees.id) AS employee_count "
        "FROM employees "
        "JOIN organization_units ON employees.organization_unit_id = organization_units.id "
        f"{province_group_where(plan, 'employees')}"
        f"{employee_attribute_clause(plan)}"
        "GROUP BY organization_units.province "
        f"ORDER BY employee_count {direction}"
        f"{limit_clause(plan)}"
    )


def employee_count_grouped_by_city(plan: SQLPlan) -> Optional[str]:
    if set(plan.required_tables) != {"employees", "organization_units"}:
        return None
    if "EMPLOYEE_COUNT_GROUPED_BY_CITY" not in _selected(plan):
        return None
    direction = ranking_direction(plan)
    return (
        "SELECT organization_units.city, COUNT(employees.id) AS employee_count "
        "FROM employees "
        "JOIN organization_units ON employees.organization_unit_id = organization_units.id "
        f"{city_group_where(plan, 'employees')}"
        f"{employee_attribute_clause(plan)}"
        "GROUP BY organization_units.city "
        f"ORDER BY employee_count {direction}"
        f"{limit_clause(plan)}"
    )


def employee_list_by_province(plan: SQLPlan) -> Optional[str]:
    if set(plan.required_tables) != {"employees", "organization_units"}:
        return None
    if "EMPLOYEE_LIST_BY_PROVINCE" not in _selected(plan):
        return None
    province = filter_value(plan, "province")
    status_filter = status_clause(plan, "employees")
    name_filter = person_name_clause(plan, "employees")
    attr_filter = employee_attribute_clause(plan)
    requested_columns = [
        column for column in plan.selected_columns if column != "EMPLOYEE_LIST_BY_PROVINCE"
    ]
    projection = _projection("employees", requested_columns)
    return (
        f"SELECT {projection}, organization_units.province, organization_units.city "
        "FROM employees "
        "JOIN organization_units ON employees.organization_unit_id = organization_units.id "
        f"WHERE organization_units.province = {sql_literal(province)} "
        f"{status_filter}"
        f"{name_filter}"
        f"{attr_filter}"
        "ORDER BY employees.last_name, employees.first_name, employees.id"
    )


def employee_count_by_city(plan: SQLPlan) -> Optional[str]:
    if set(plan.required_tables) != {"employees", "organization_units"}:
        return None
    if "EMPLOYEE_COUNT_BY_CITY" not in _selected(plan):
        return None
    city = filter_value(plan, "city")
    status_filter = status_clause(plan, "employees")
    name_filter = person_name_clause(plan, "employees")
    attr_filter = employee_attribute_clause(plan)
    return (
        "SELECT organization_units.city, COUNT(employees.id) AS employee_count "
        "FROM employees "
        "JOIN organization_units ON employees.organization_unit_id = organization_units.id "
        f"WHERE organization_units.city = {sql_literal(city)} "
        f"{status_filter}"
        f"{name_filter}"
        f"{attr_filter}"
        "GROUP BY organization_units.city"
    )


def employee_list_by_city(plan: SQLPlan) -> Optional[str]:
    if set(plan.required_tables) != {"employees", "organization_units"}:
        return None
    if "EMPLOYEE_LIST_BY_CITY" not in _selected(plan):
        return None
    city = filter_value(plan, "city")
    status_filter = status_clause(plan, "employees")
    name_filter = person_name_clause(plan, "employees")
    attr_filter = employee_attribute_clause(plan)
    requested_columns = [
        column for column in plan.selected_columns if column != "EMPLOYEE_LIST_BY_CITY"
    ]
    projection = _projection("employees", requested_columns)
    return (
        f"SELECT {projection}, organization_units.province, organization_units.city "
        "FROM employees "
        "JOIN organization_units ON employees.organization_unit_id = organization_units.id "
        f"WHERE organization_units.city = {sql_literal(city)} "
        f"{status_filter}"
        f"{name_filter}"
        f"{attr_filter}"
        "ORDER BY employees.last_name, employees.first_name, employees.id"
    )


def employee_count_by_status(plan: SQLPlan) -> Optional[str]:
    if set(plan.required_tables) != {"employees"}:
        return None
    if "EMPLOYEE_COUNT_BY_STATUS" not in _selected(plan):
        return None
    status = filter_value(plan, "status")
    attr_filter = employee_attribute_clause(plan)
    return (
        "SELECT employees.status, COUNT(employees.id) AS employee_count "
        "FROM employees "
        f"WHERE employees.status = {sql_literal(status)} "
        f"{attr_filter}"
        "GROUP BY employees.status"
    )


def employee_list_by_status(plan: SQLPlan) -> Optional[str]:
    if set(plan.required_tables) != {"employees"}:
        return None
    if "EMPLOYEE_LIST_BY_STATUS" not in _selected(plan):
        return None
    status = filter_value(plan, "status")
    requested_columns = [
        column for column in plan.selected_columns if column != "EMPLOYEE_LIST_BY_STATUS"
    ]
    projection = _projection("employees", requested_columns)
    return (
        f"SELECT {projection} "
        "FROM employees "
        f"WHERE employees.status = {sql_literal(status)} "
        f"{person_name_clause(plan, 'employees')}"
        f"{employee_attribute_clause(plan)}"
        "ORDER BY employees.last_name, employees.first_name, employees.id"
    )


def employee_count_by_name(plan: SQLPlan) -> Optional[str]:
    if set(plan.required_tables) != {"employees"}:
        return None
    if "EMPLOYEE_COUNT_BY_NAME" not in _selected(plan):
        return None
    where = person_name_clause(plan, "employees", prefix="WHERE")
    attr_filter = employee_attribute_clause(plan)
    return (
        "SELECT COUNT(employees.id) AS employee_count "
        "FROM employees "
        f"{where}"
        f"{attr_filter}"
    )


def employee_list_by_name(plan: SQLPlan) -> Optional[str]:
    if set(plan.required_tables) != {"employees"}:
        return None
    if "EMPLOYEE_LIST_BY_NAME" not in _selected(plan):
        return None
    requested_columns = [
        column for column in plan.selected_columns if column != "EMPLOYEE_LIST_BY_NAME"
    ]
    projection = _projection("employees", requested_columns)
    where = person_name_clause(plan, "employees", prefix="WHERE")
    attr_filter = employee_attribute_clause(plan)
    return (
        f"SELECT {projection} "
        "FROM employees "
        f"{where}"
        f"{attr_filter}"
        "ORDER BY employees.last_name, employees.first_name, employees.id"
    )


def employee_count_total(plan: SQLPlan) -> Optional[str]:
    if set(plan.required_tables) != {"employees"}:
        return None
    if "EMPLOYEE_COUNT_TOTAL" not in _selected(plan):
        return None
    clauses = []
    status = filter_value(plan, "status")
    if status:
        clauses.append(f"employees.status = {sql_literal(status)}")
    position = filter_value(plan, "position")
    hire_year = filter_value(plan, "hire_year")
    if position:
        clauses.append(f"employees.position = {sql_literal(position)}")
    if hire_year:
        clauses.append(f"EXTRACT(YEAR FROM employees.hire_date) = {int(hire_year)}")
    where = " WHERE " + " AND ".join(clauses) if clauses else ""
    return f"SELECT COUNT(employees.id) AS total_employees FROM employees{where}"


def employee_list_filtered(plan: SQLPlan) -> Optional[str]:
    if set(plan.required_tables) != {"employees"}:
        return None
    if "EMPLOYEE_LIST_FILTERED" not in _selected(plan):
        return None
    requested_columns = [
        column for column in plan.selected_columns if column != "EMPLOYEE_LIST_FILTERED"
    ]
    projection = _projection("employees", requested_columns)
    attr_filter = employee_attribute_clause(plan, prefix="WHERE")
    return (
        f"SELECT {projection} "
        "FROM employees "
        f"{attr_filter}"
        "ORDER BY employees.last_name, employees.first_name, employees.id"
    )


def employee_by_national_id(plan: SQLPlan) -> Optional[str]:
    if set(plan.required_tables) != {"employees"}:
        return None
    if not ({"EMPLOYEE_IDENTITY_BY_NATIONAL_ID", "EMPLOYEE_BY_NATIONAL_ID"} & _selected(plan)):
        return None
    national_id = filter_value(plan, "national_id")
    requested_columns = [
        column
        for column in plan.selected_columns
        if column not in {"EMPLOYEE_IDENTITY_BY_NATIONAL_ID", "EMPLOYEE_BY_NATIONAL_ID"}
    ]
    projection = _projection("employees", requested_columns)
    return (
        f"SELECT {projection} "
        "FROM employees "
        f"WHERE employees.national_id = {sql_literal(national_id)}"
    )


def employee_pension_amount_by_national_id(plan: SQLPlan) -> Optional[str]:
    if set(plan.required_tables) != {"employees", "retirement_records"}:
        return None
    if "EMPLOYEE_PENSION_AMOUNT_BY_NATIONAL_ID" not in _selected(plan):
        return None
    national_id = filter_value(plan, "national_id")
    return (
        "SELECT employees.first_name, employees.last_name, employees.national_id, "
        "retirement_records.years_of_service, retirement_records.pension_amount, "
        "retirement_records.retirement_date, retirement_records.retirement_type "
        "FROM employees "
        "JOIN retirement_records ON retirement_records.employee_id = employees.id "
        f"WHERE employees.national_id = {sql_literal(national_id)}"
    )


def retirement_pension_amount_by_employee(plan: SQLPlan) -> Optional[str]:
    if set(plan.required_tables) != {"employees", "retirement_records"} or plan.limit != 1:
        return None
    if "RETIREMENT_PENSION_AMOUNT_BY_EMPLOYEE" not in _selected(plan):
        return None
    direction = "ASC" if plan.order_by and "ASC" in plan.order_by.upper() else "DESC"
    return (
        "SELECT employees.first_name, employees.last_name, employees.national_id, "
        "retirement_records.years_of_service, retirement_records.pension_amount, "
        "retirement_records.retirement_date, retirement_records.retirement_type "
        "FROM retirement_records "
        "JOIN employees ON retirement_records.employee_id = employees.id "
        f"ORDER BY retirement_records.pension_amount {direction} "
        "LIMIT 1"
    )


def salary_base_net_average(plan: SQLPlan) -> Optional[str]:
    if set(plan.required_tables) not in ({"salary_items", "employees"}, {"salary_items", "employees", "organization_units"}):
        return None
    if not any("BASE_SALARY" in column.upper() for column in plan.selected_columns):
        return None
    return (
        "SELECT "
        "AVG(salary_items.base_salary) AS avg_base_salary, "
        "AVG(salary_items.net_salary) AS avg_net_salary, "
        "AVG(salary_items.net_salary - salary_items.base_salary) AS avg_difference "
        "FROM salary_items "
        f"{salary_joins(plan)}"
        f"{salary_where_clause(plan)}"
    )


def salary_total_by_employee(plan: SQLPlan) -> Optional[str]:
    if set(plan.required_tables) not in ({"salary_items", "employees"}, {"salary_items", "employees", "organization_units"}) or plan.limit != 1:
        return None
    direction = "ASC" if plan.order_by and "ASC" in plan.order_by.upper() else "DESC"
    return (
        "SELECT employees.first_name, employees.last_name, "
        "SUM(salary_items.allowances) AS total_salary "
        "FROM salary_items "
        f"{salary_joins(plan)}"
        f"{salary_where_clause(plan)}"
        "GROUP BY employees.id, employees.first_name, employees.last_name "
        f"ORDER BY total_salary {direction} "
        "LIMIT 1"
    )


def school_count_by_province_fallback(plan: SQLPlan) -> Optional[str]:
    if set(plan.required_tables) != {"schools", "organization_units"}:
        return None
    return (
        "SELECT organization_units.province, COUNT(schools.id) AS school_count "
        "FROM schools "
        "JOIN organization_units ON schools.organization_unit_id = organization_units.id "
        "GROUP BY organization_units.province "
        "ORDER BY school_count DESC"
    )


def pending_ranking_requests(plan: SQLPlan) -> Optional[str]:
    if set(plan.required_tables) != {"ranking_requests"}:
        return None
    if not any(item.get("column") == "status" and item.get("value") == "pending" for item in plan.filters):
        return None
    return (
        "SELECT ranking_requests.id, ranking_requests.employee_id, ranking_requests.status "
        "FROM ranking_requests "
        "WHERE ranking_requests.status = 'pending'"
    )


TEMPLATES: list[TemplateFn] = [
    training_request_count,
    training_request_list,
    training_request_cost_sum,
    training_request_cost_avg,
    training_request_ranked_cost,
    generic_table_count,
    generic_table_aggregate,
    generic_table_list,
    composable_counts_by_province,
    composable_counts_by_city,
    student_total_count,
    student_count_grouped_by_province,
    student_count_grouped_by_city,
    student_list_by_status,
    student_count_by_name,
    student_list_by_name,
    student_school_name_by_name,
    student_by_national_id,
    student_count_by_province,
    student_list_by_province,
    student_count_by_city,
    student_list_by_city,
    student_list_by_school_name,
    student_count_by_school_name,
    school_names_by_province,
    school_count_by_province,
    school_names_by_city,
    school_count_by_city,
    school_count_grouped_by_province,
    school_count_grouped_by_city,
    school_names_by_org_unit_name,
    school_count_by_org_unit_name,
    school_phone_by_name,
    organization_unit_by_name,
    school_by_name,
    school_count_filtered,
    school_list_filtered,
    employee_count_by_province,
    employee_count_grouped_by_province,
    employee_count_grouped_by_city,
    employee_list_by_province,
    employee_count_by_city,
    employee_list_by_city,
    employee_count_by_status,
    employee_list_by_status,
    employee_count_by_name,
    employee_list_by_name,
    employee_count_total,
    employee_list_filtered,
    employee_pension_amount_by_national_id,
    retirement_pension_amount_by_employee,
    employee_by_national_id,
    salary_base_net_average,
    salary_total_by_employee,
    pending_ranking_requests,
    school_count_by_province_fallback,
]


def render_template_sql(plan: SQLPlan) -> Optional[str]:
    for template in TEMPLATES:
        sql = template(plan)
        if sql:
            return sql
    return None
