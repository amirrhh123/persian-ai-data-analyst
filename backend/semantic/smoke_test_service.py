import json
import re
from pathlib import Path
from typing import Optional

from backend.config import get_settings
from backend.database.onboarding_service import database_onboarding_service
from backend.database.models import DiscoveredColumnInfo, DiscoveredTableInfo, SchemaDiscoverySnapshot
from backend.semantic.models import SemanticSmokeTestCase, SemanticSmokeTestGenerationResponse


OUTPUT_DIR = Path(__file__).parent.parent.parent / "tests" / "benchmark"
DEFAULT_OUTPUT_PATH = OUTPUT_DIR / "generated_smoke_cases.json"

TEXT_TYPES = {"character varying", "character", "text", "USER-DEFINED"}
NUMERIC_TYPES = {"integer", "bigint", "numeric", "double precision", "real", "decimal"}
DATE_TYPES = {"date", "timestamp without time zone", "timestamp with time zone"}


class SemanticSmokeTestService:
    def __init__(self):
        self.settings = get_settings()

    def generate(
        self,
        tenant_id: Optional[str] = None,
        max_cases_per_table: int = 5,
    ) -> SemanticSmokeTestGenerationResponse:
        tenant = tenant_id or self.settings.tenant_id
        snapshot = database_onboarding_service.load_snapshot(tenant)
        if snapshot is None:
            return SemanticSmokeTestGenerationResponse(
                status="blocked",
                tenant_id=tenant,
                cases=[],
            )

        cases: list[SemanticSmokeTestCase] = []
        for table in snapshot.tables:
            table_cases = self._table_cases(table)
            cases.extend(table_cases[:max_cases_per_table])

        return SemanticSmokeTestGenerationResponse(
            status="success",
            tenant_id=tenant,
            source_fingerprint=snapshot.fingerprint,
            cases=cases,
        )

    def sync(
        self,
        tenant_id: Optional[str] = None,
        max_cases_per_table: int = 5,
        output_path: Optional[Path] = None,
    ) -> SemanticSmokeTestGenerationResponse:
        response = self.generate(tenant_id=tenant_id, max_cases_per_table=max_cases_per_table)
        if response.status != "success":
            return response
        path = output_path or DEFAULT_OUTPUT_PATH
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as file:
            json.dump([case.model_dump(mode="json") for case in response.cases], file, ensure_ascii=False, indent=2)
        response.output_path = str(path)
        return response

    def _table_cases(self, table: DiscoveredTableInfo) -> list[SemanticSmokeTestCase]:
        label = self._table_label(table.name)
        cases = [
            SemanticSmokeTestCase(
                id=self._case_id(table.name, "count"),
                table=table.name,
                kind="count",
                question=f"تعداد رکوردهای جدول {label} را بگو",
                expected={
                    "requested_table": table.name,
                    "aggregation": "COUNT",
                    "sql_contains": [f"FROM {table.name}", "COUNT("],
                },
            ),
            SemanticSmokeTestCase(
                id=self._case_id(table.name, "list"),
                table=table.name,
                kind="list",
                question=f"لیست اطلاعات جدول {label} را نشان بده",
                expected={
                    "requested_table": table.name,
                    "wants_list": True,
                    "sql_contains": [f"FROM {table.name}", "LIMIT"],
                },
            ),
        ]

        text_column = self._first_text_sample_column(table)
        if text_column:
            sample = text_column.sample_values[0].value
            cases.append(
                SemanticSmokeTestCase(
                    id=self._case_id(table.name, f"filter_{text_column.name}"),
                    table=table.name,
                    kind="sample_filter",
                    question=f"اطلاعات جدول {label} با {self._column_label(text_column.name)} {sample} را نشان بده",
                    expected={
                        "requested_table": table.name,
                        "filters": {text_column.name: sample},
                        "sql_contains": [f"FROM {table.name}", text_column.name, str(sample)],
                    },
                )
            )
            cases.append(
                SemanticSmokeTestCase(
                    id=self._case_id(table.name, f"group_by_{text_column.name}"),
                    table=table.name,
                    kind="group_by",
                    question=f"تعداد رکوردهای جدول {label} را به تفکیک {self._column_label(text_column.name)} بگو",
                    expected={
                        "requested_table": table.name,
                        "aggregation": "COUNT",
                        "group_by": text_column.name,
                        "sql_contains": [f"FROM {table.name}", "COUNT(", "GROUP BY", text_column.name],
                    },
                )
            )

        numeric_column = self._first_numeric_measure_column(table)
        if numeric_column:
            cases.append(
                SemanticSmokeTestCase(
                    id=self._case_id(table.name, f"max_{numeric_column.name}"),
                    table=table.name,
                    kind="max",
                    question=f"بیشترین {self._column_label(numeric_column.name)} در جدول {label} را بگو",
                    expected={
                        "requested_table": table.name,
                        "aggregation": "MAX",
                        "metric": numeric_column.name,
                        "sql_contains": [f"FROM {table.name}", numeric_column.name],
                    },
                )
            )

        date_column = self._first_date_column(table)
        if date_column:
            cases.append(
                SemanticSmokeTestCase(
                    id=self._case_id(table.name, f"recent_{date_column.name}"),
                    table=table.name,
                    kind="recent",
                    question=f"جدیدترین رکوردهای جدول {label} بر اساس {self._column_label(date_column.name)} را نشان بده",
                    expected={
                        "requested_table": table.name,
                        "sorting": date_column.name,
                        "sql_contains": [f"FROM {table.name}", "ORDER BY", date_column.name, "LIMIT"],
                    },
                )
            )

        return cases

    def _first_text_sample_column(self, table: DiscoveredTableInfo) -> DiscoveredColumnInfo | None:
        return next(
            (
                column
                for column in table.columns
                if column.data_type in TEXT_TYPES
                and not column.is_primary_key
                and not column.name.endswith("_id")
                and column.sample_values
            ),
            None,
        )

    def _first_numeric_measure_column(self, table: DiscoveredTableInfo) -> DiscoveredColumnInfo | None:
        return next(
            (
                column
                for column in table.columns
                if column.data_type in NUMERIC_TYPES
                and not column.is_primary_key
                and not column.name.endswith("_id")
                and column.name != "id"
            ),
            None,
        )

    def _first_date_column(self, table: DiscoveredTableInfo) -> DiscoveredColumnInfo | None:
        return next((column for column in table.columns if column.data_type in DATE_TYPES or column.name.endswith("_at")), None)

    def _table_label(self, name: str) -> str:
        return name.replace("_", " ")

    def _column_label(self, name: str) -> str:
        return name.replace("_", " ")

    def _case_id(self, table_name: str, kind: str) -> str:
        safe_table = re.sub(r"[^a-z0-9_]+", "_", table_name.lower())
        safe_kind = re.sub(r"[^a-z0-9_]+", "_", kind.lower())
        return f"smoke_{safe_table}_{safe_kind}"


semantic_smoke_test_service = SemanticSmokeTestService()
