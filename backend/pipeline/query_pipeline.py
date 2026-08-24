import json
import re
import time
from pathlib import Path
from typing import List, Optional
from uuid import uuid4

from backend.answer.service import answer_service
from backend.citations.service import citation_service
from backend.config import get_settings
from backend.database.models import DatabaseSchema, RelationshipInfo, SchemaDiscoverySnapshot
from backend.database.sync_service import schema_sync_service
from backend.execution.models import QueryRequest
from backend.execution.service import execution_service
from backend.explainability.service import explainability_service
from backend.knowledge.loader import KnowledgeLoader
from backend.knowledge.models import Report
from backend.pipeline.intent import (
    detect_ambiguity,
    extract_intent,
    normalize_intent,
    suppress_name_substring_columns,
)
from backend.pipeline.clarification_state import (
    ClarificationContext,
    clarification_store,
)
from backend.pipeline.confidence_policy import (
    DECISION_CLARIFY,
    confidence_policy,
    table_label_fa,
)
from backend.pipeline.error_taxonomy import pipeline_error_taxonomy
from backend.pipeline.models import PipelineRequest, PipelineResponse
from backend.pipeline.school_resolver import resolve_school_name
from backend.pipeline.trace import PipelineTracer
from backend.pipeline.safety.intent_detector import safety_detector
from backend.pipeline.safety.unsupported_detector import unsupported_detector
from backend.pipeline.safety.multi_intent_detector import multi_intent_detector
from backend.reports.group_retriever import group_retriever
from backend.reports.retriever import report_retriever
from backend.semantic.loader import load_tenant_semantic_catalog
from backend.semantic.models import SemanticCatalog, SemanticTable, normalize_identifier
from backend.semantic.resolver import semantic_resolver
from backend.semantic.snapshot import SemanticSnapshot, semantic_snapshot_provider
from backend.security.data_policy import data_sensitivity_policy
from backend.sql.aggregate_guard import sql_aggregate_safety_guard
from backend.sql.deterministic_builder import deterministic_sql_builder
from backend.sql.filter_contract import build_filter_contract
from backend.sql.generator import sql_generator
from backend.sql.identifier_canonicalizer import canonicalize_sql_identifiers
from backend.sql.join_verifier import sql_plan_join_verifier
from backend.sql.models import SQLPlan
from backend.sql.planner import sql_planner
from backend.sql.result_contract import build_result_contract, validate_plan_shape
from backend.sql.result_shape_validator import sql_result_shape_validator
from backend.sql.validator import sql_validator
from backend.value_index.resolver import GroundingResult, value_grounding_resolver
from backend.value_index.ranker import ENTITY_PRIMARY_TABLES
from backend.value_index.service import value_index_service


class QueryPipeline:
    KNOWN_ENTITY_ROUTING = {
        "student", "employee", "school", "salary", "retirement",
        "ranking", "organization",
    }

    def __init__(self):
        self.settings = get_settings()
        self.tenants_dir = Path(__file__).parent.parent.parent / "knowledge" / "tenants"
        self._last_related_ambiguity: Optional[dict[str, object]] = None
        self.legacy_routed_tables = {
            "employees",
            "students",
            "schools",
            "organization_units",
            "salary_items",
            "ranking_requests",
            "retirement_records",
        }

    def _get_report(self, tenant_id: str, report_id: str) -> Optional[Report]:
        tenant_path = self.tenants_dir / tenant_id
        loader = KnowledgeLoader(tenant_path)
        for report in loader.load_all_reports():
            if report.id == report_id:
                return report
        return None

    def _ground_question_values(
        self,
        question: str,
        tenant_id: str,
        intent,
        catalog: SemanticCatalog,
    ) -> GroundingResult:
        """Ground literal values onto real columns; never breaks the pipeline."""
        self._last_grounding_error: Optional[str] = None
        try:
            snapshot = value_index_service.load(tenant_id)
            return value_grounding_resolver.resolve(
                question,
                snapshot,
                requested_entity=intent.requested_entity,
            )
        except Exception as exc:
            self._last_grounding_error = f"{type(exc).__name__}: {exc}"
            return GroundingResult()

    @staticmethod
    def _intent_has_binding_scalars(intent) -> bool:
        """True when explicit filters bind the question to the entity's table."""
        return any(
            [
                getattr(intent, "national_id", None),
                getattr(intent, "first_name", None),
                getattr(intent, "last_name", None),
                getattr(intent, "named_student", None),
                getattr(intent, "named_employee", None),
                getattr(intent, "province", None),
                getattr(intent, "city", None),
                getattr(intent, "status", None),
                getattr(intent, "position", None),
                getattr(intent, "grade", None),
                getattr(intent, "enrollment_year", None),
                getattr(intent, "hire_year", None),
                getattr(intent, "named_school", None),
                getattr(intent, "named_organization_unit", None),
                getattr(intent, "province_values", None),
                getattr(intent, "city_values", None),
                getattr(intent, "school_type", None),
                getattr(intent, "capacity_min", None),
                getattr(intent, "established_year", None),
                getattr(intent, "date_range", None),
            ]
        )

    def _grounding_overrides_entity(
        self,
        grounding: GroundingResult,
        intent,
        catalog: SemanticCatalog,
        question: str,
    ) -> bool:
        """Allow rerouting only when the entity word is part of a grounded value.

        Example: «کارمند اداری» is a requester_role VALUE that merely starts
        with the employee alias «کارمند»; the value evidence wins. Explicit
        binding scalars always keep the deterministic entity path.
        """
        if not grounding.grounded_filters:
            return False
        top = grounding.grounded_filters[0]
        # Score floor aligns with the policy's validated band; the decisive
        # safety signals below are exact value containment and alias prefix.
        if top.score < 0.60:
            return False
        if self._intent_has_binding_scalars(intent):
            return False
        recommended = grounding.recommended_table
        if not recommended or recommended == ENTITY_PRIMARY_TABLES.get(intent.requested_entity):
            return False
        recommended_table = catalog.table(recommended)
        if not recommended_table:
            return False

        normalized_question = normalize_identifier(question)
        normalized_value = normalize_identifier(top.value)
        if normalized_value not in normalized_question:
            return False
        entity_table_name = ENTITY_PRIMARY_TABLES.get(intent.requested_entity, "")
        entity_table = catalog.table(entity_table_name)
        if not entity_table:
            return True
        return any(
            normalize_identifier(alias) and normalize_identifier(alias) in normalized_value
            for alias in (entity_table.aliases or [])
        )

    def _load_discovery_snapshot(self, tenant_id: Optional[str] = None) -> Optional[SchemaDiscoverySnapshot]:
        tenant = tenant_id or self.settings.tenant_id
        path = Path(__file__).parent.parent.parent / "schema" / "tenants" / tenant / "discovery.json"
        if not path.exists():
            return None
        with path.open("r", encoding="utf-8") as file:
            return SchemaDiscoverySnapshot.model_validate(json.load(file))

    def _normalize_text(self, value: str) -> str:
        return normalize_identifier(value.replace("‌", " ").replace("ي", "ی").replace("ك", "ک"))

    def _semantic_target_table(self, question: str, catalog: SemanticCatalog) -> Optional[SemanticTable]:
        text = self._normalize_text(question)
        best_table = None
        best_score = 0
        for table in catalog.tables:
            if table.name in self.legacy_routed_tables:
                continue
            aliases = [table.name, table.entity, table.description, *table.aliases]
            for alias in aliases:
                normalized_alias = self._normalize_text(alias or "")
                if not normalized_alias or len(normalized_alias) < 4:
                    continue
                if normalized_alias in text:
                    score = len(normalized_alias)
                    if score > best_score:
                        best_table = table
                        best_score = score
        return best_table

    def _mentions_legacy_entity(self, question: str) -> bool:
        text = self._normalize_text(question)
        legacy_terms = [
            "دانش آموز",
            "دانش آموزان",
            "دانش‌آموز",
            "دانش‌آموزان",
            "محصل",
            "کارمندان",
            "پرسنل",
            "معلمان",
            "مدرسه",
            "مدارس",
            "دبستان",
            "دبیرستان",
            "هنرستان",
            "حقوق",
            "حقوقی",
            "سنوات",
            "بازنشستگی",
            "رتبه بندی",
            "رتبه‌بندی",
            "کد ملی",
            "سازمان",
            "اداره کل",
            "منطقه آموزشی",
        ]
        return any(term in text for term in legacy_terms)

    def _sample_value_mentions_for_table(
        self,
        question: str,
        table: SemanticTable,
        discovery: SchemaDiscoverySnapshot,
    ) -> list[tuple[str, str, int, int]]:
        indexed_matches = value_index_service.search(
            question,
            tenant_id=self.settings.tenant_id,
            table=table.name,
        )
        if indexed_matches:
            return [
                (
                    match.column,
                    match.value,
                    len(self._normalize_text(match.value)),
                    match.count,
                )
                for match in indexed_matches
            ]

        text = question.replace("‌", " ")
        discovered_table = next((item for item in discovery.tables if item.name == table.name), None)
        if not discovered_table:
            return []

        matches = []
        for column in discovered_table.columns:
            if column.is_primary_key or column.name.endswith("_id"):
                continue
            for sample in column.sample_values:
                value = (sample.value or "").replace("‌", " ").strip()
                if len(value) < 2:
                    continue
                if re.search(rf"(?<!\S){re.escape(value)}(?!\S)", text):
                    matches.append((column.name, sample.value or value, len(value), sample.count))
        matches.sort(key=lambda item: (item[2], item[3]), reverse=True)
        return matches

    def _labeled_sample_value_mentions_for_table(
        self,
        question: str,
        table: SemanticTable,
        discovery: SchemaDiscoverySnapshot,
    ) -> list[tuple[str, str, int, int]]:
        indexed_matches = [
            match
            for match in value_index_service.search(
                question,
                tenant_id=self.settings.tenant_id,
                table=table.name,
            )
            if match.label_matched
        ]
        if indexed_matches:
            return [
                (
                    match.column,
                    match.value,
                    len(self._normalize_text(match.value)),
                    match.count,
                )
                for match in indexed_matches
            ]

        text = question.replace("‌", " ")
        discovered_table = next((item for item in discovery.tables if item.name == table.name), None)
        if not discovered_table:
            return []

        discovered_columns = {column.name: column for column in discovered_table.columns}
        matches = []
        for semantic_column in table.columns:
            discovered_column = discovered_columns.get(semantic_column.name)
            if (
                not discovered_column
                or discovered_column.is_primary_key
                or discovered_column.name.endswith("_id")
                or semantic_column.data_type in {"integer", "bigint", "numeric", "double precision", "real"}
            ):
                continue
            labels = [
                (label or "").replace("‌", " ").strip()
                for label in [semantic_column.name, *semantic_column.aliases]
                if label and len((label or "").replace("‌", " ").strip()) >= 2
            ]
            if not labels:
                continue
            for sample in discovered_column.sample_values:
                value = (sample.value or "").replace("‌", " ").strip()
                if len(value) < 2:
                    continue
                if any(re.search(rf"(?<!\S){re.escape(label)}\s+{re.escape(value)}(?!\S)", text) for label in labels):
                    matches.append((semantic_column.name, sample.value or value, len(value), sample.count))
        matches.sort(key=lambda item: (item[2], item[3]), reverse=True)
        return matches

    def _semantic_target_table_by_sample_values(
        self,
        question: str,
        catalog: SemanticCatalog,
    ) -> Optional[SemanticTable]:
        text = self._normalize_text(question)
        if self._mentions_legacy_entity(question):
            return None
        generic_entity_terms = [
            "درخواست",
            "رکورد",
            "مورد",
            "موارد",
            "اطلاعات",
            "لیست",
            "فهرست",
            "تعداد",
            "چند",
        ]
        if not any(term in text for term in generic_entity_terms):
            return None

        discovery = self._load_discovery_snapshot()
        if not discovery:
            return None

        candidates: list[tuple[SemanticTable, str, str, int, int]] = []
        for table in catalog.tables:
            if table.name in self.legacy_routed_tables:
                continue
            for column_name, value, value_len, count in self._sample_value_mentions_for_table(question, table, discovery):
                candidates.append((table, column_name, value, value_len, count))

        if not candidates:
            return None
        candidates.sort(key=lambda item: (item[3], item[4]), reverse=True)
        best_table, _, best_value, _, _ = candidates[0]
        tied_tables = {table.name for table, _, value, _, _ in candidates if value == best_value}
        if len(tied_tables) > 1:
            return None
        return best_table

    def _semantic_target_table_by_labeled_sample_values(
        self,
        question: str,
        catalog: SemanticCatalog,
    ) -> Optional[SemanticTable]:
        if self._mentions_legacy_entity(question):
            return None
        discovery = self._load_discovery_snapshot()
        if not discovery:
            return None

        candidates: list[tuple[SemanticTable, str, str, int, int]] = []
        for table in catalog.tables:
            if table.name in self.legacy_routed_tables:
                continue
            for column_name, value, value_len, count in self._labeled_sample_value_mentions_for_table(question, table, discovery):
                candidates.append((table, column_name, value, value_len, count))

        if not candidates:
            return None
        candidates.sort(key=lambda item: (item[3], item[4]), reverse=True)
        best_table, best_column, best_value, _, _ = candidates[0]
        tied_targets = {
            (table.name, column_name)
            for table, column_name, value, _, _ in candidates
            if column_name == best_column and value == best_value
        }
        if len(tied_targets) > 1:
            return None
        return best_table

    def _is_training_request_question(self, question: str, catalog: SemanticCatalog) -> bool:
        text = self._normalize_text(question)
        if any(term in text for term in ["رتبه بندی", "رتبه‌بندی", "رتبه", "ارتقا"]):
            return False
        # Generic "موارد/رکوردها" questions are training-request queries;
        # do not let a province sample value route them to organization_units.
        if re.search(r"(?:تعداد|لیست|فهرست)\s+(?:موارد|مورد|رکوردها?)\b", text) and not any(
            term in text for term in ["دانش آموز", "دانش‌آموز", "کارمند", "مدرسه", "سازمانی"]
        ):
            return True
        table = self._semantic_target_table(question, catalog)
        if not table:
            table = self._semantic_target_table_by_labeled_sample_values(question, catalog)
        if not table:
            table = self._semantic_target_table_by_sample_values(question, catalog)
        if table and table.name == "demo_training_requests":
            return True
        return any(alias in text for alias in ["درخواست آموزشی", "دوره", "کارگاه", "آموزش"])

    def _extract_value_after_any(self, text: str, labels: list[str], allowed_values: list[str]) -> Optional[str]:
        normalized = text.replace("‌", " ")
        for value in allowed_values:
            if value in normalized and any(label in normalized for label in labels):
                return value
        for label in labels:
            pattern = rf"(?:با\s+)?{re.escape(label)}\s+(.+?)(?:\s+(?:و|در|استان|شهر|با)\s+|$)"
            match = re.search(pattern, normalized)
            if match:
                candidate = match.group(1).strip(" ؟?،,")
                for value in allowed_values:
                    if value in candidate or candidate in value:
                        return value
                if candidate:
                    return candidate
        return None

    def _dedupe_filters(self, filters: list[dict[str, str]]) -> list[dict[str, str]]:
        deduped = []
        seen = set()
        for item in filters:
            key = (item["column"], item["operator"])
            if key not in seen:
                deduped.append(item)
                seen.add(key)
        return deduped

    def _semantic_filters_for_table(self, question: str, table: SemanticTable) -> list[dict[str, str]]:
        text = question.replace("‌", " ")
        filters: list[dict[str, str]] = []
        stop_pattern = r"(?:\s+(?:و|در|استان|شهر|با|که|را|رو)\s+|$)"
        for column in table.columns:
            labels = [column.name, *column.aliases]
            for label in labels:
                normalized_label = (label or "").replace("‌", " ").strip()
                if not normalized_label or len(normalized_label) < 2:
                    continue
                pattern = rf"با\s+{re.escape(normalized_label)}\s+(.+?){stop_pattern}"
                match = re.search(pattern, text)
                if match:
                    value = match.group(1).strip(" ؟?،,")
                    if column.data_type in {"integer", "bigint", "numeric", "double precision", "real"} and (
                        value.startswith("بیشتر")
                        or value.startswith("کمتر")
                        or value.startswith("بالای")
                        or value.startswith("زیر")
                        or value.startswith("حداقل")
                        or value.startswith("حداکثر")
                        or value.startswith("بیش از")
                        or value.startswith("بالاتر")
                        or value.startswith("پایین")
                    ):
                        continue
                    if value:
                        filters.append({"column": column.name, "operator": "=", "value": value})
                        break
        return self._dedupe_filters(filters)

    def _labeled_value_filters_for_table(
        self,
        question: str,
        table: SemanticTable,
        existing_filters: list[dict[str, str]],
    ) -> list[dict[str, str]]:
        discovery = self._load_discovery_snapshot()
        if not discovery:
            return []

        existing_columns = {item["column"] for item in existing_filters}
        filters = []
        for column_name, value, _, _ in self._labeled_sample_value_mentions_for_table(question, table, discovery):
            if column_name not in existing_columns:
                filters.append({"column": column_name, "operator": "=", "value": value})
        return self._dedupe_filters(filters)

    def _related_labeled_value_filters_for_table(
        self,
        question: str,
        target_table: SemanticTable,
        catalog: SemanticCatalog,
        existing_filters: list[dict[str, str]],
    ) -> tuple[list[dict[str, str]], list[str]]:
        discovery = self._load_discovery_snapshot()
        if not discovery:
            return [], []

        relationships = self._schema_relationships(catalog)
        existing_columns = {item["column"] for item in existing_filters}
        filters = []
        related_tables = []
        for table in catalog.tables:
            if table.name == target_table.name:
                continue
            path = sql_planner.expand_required_tables([target_table.name, table.name], relationships)
            if table.name not in path or len(path) < 2:
                continue
            for column_name, value, _, _ in self._labeled_sample_value_mentions_for_table(question, table, discovery):
                qualified_column = f"{table.name}.{column_name}"
                if qualified_column in existing_columns or column_name in existing_columns:
                    continue
                filters.append({"column": qualified_column, "operator": "=", "value": value})
                if table.name not in related_tables:
                    related_tables.append(table.name)
        return self._dedupe_filters(filters), related_tables

    def _related_numeric_filters_for_table(
        self,
        question: str,
        target_table: SemanticTable,
        catalog: SemanticCatalog,
        existing_filters: list[dict[str, str]],
    ) -> tuple[list[dict[str, str]], list[str]]:
        relationships = self._schema_relationships(catalog)
        candidates: list[tuple[str, dict[str, str]]] = []
        for table in catalog.tables:
            if table.name == target_table.name:
                continue
            path = sql_planner.expand_required_tables([target_table.name, table.name], relationships)
            if table.name not in path or len(path) < 2:
                continue
            table_filters = self._numeric_filters_for_table(
                question,
                table,
                existing_filters,
                column_prefix=table.name,
            )
            for item in table_filters:
                candidates.append((table.name, item))

        grouped: dict[tuple[str, str, str], set[str]] = {}
        for table_name, item in candidates:
            key = (item["operator"], item["value"], item["column"].split(".", 1)[-1])
            grouped.setdefault(key, set()).add(table_name)

        ambiguous = [
            {"operator": operator, "value": value, "column": column, "tables": sorted(tables)}
            for (operator, value, column), tables in grouped.items()
            if len(tables) > 1
        ]
        if ambiguous:
            self._last_related_ambiguity = {
                "type": "related_numeric_filter",
                "items": ambiguous,
            }

        filters = []
        related_tables = []
        for table_name, item in candidates:
            key = (item["operator"], item["value"], item["column"].split(".", 1)[-1])
            if len(grouped.get(key, set())) > 1:
                continue
            filters.append(item)
            if table_name not in related_tables:
                related_tables.append(table_name)
        return self._dedupe_filters(filters), related_tables

    def _group_by_columns_for_table(
        self,
        question: str,
        table: SemanticTable,
        column_prefix: str = "",
    ) -> list[str]:
        text = question.replace("‌", " ")
        group_markers = ["به تفکیک", "بر اساس", "براساس", "گروه بندی", "گروه‌بندی"]
        if not any(marker in text for marker in group_markers):
            return []
        group_text = text
        for marker in group_markers:
            if marker in text:
                group_text = text.split(marker, 1)[1]
                break
        columns = []
        for column in table.columns:
            labels = [
                (label or "").replace("‌", " ").strip()
                for label in [column.name, *column.aliases]
                if label and len((label or "").replace("‌", " ").strip()) >= 2
            ]
            if any(label in group_text for label in labels):
                columns.append(f"{column_prefix}.{column.name}" if column_prefix else column.name)
        return columns

    def _related_group_by_columns_for_table(
        self,
        question: str,
        target_table: SemanticTable,
        catalog: SemanticCatalog,
    ) -> tuple[list[str], list[str]]:
        relationships = self._schema_relationships(catalog)
        group_by = []
        related_tables = []
        for table in catalog.tables:
            if table.name == target_table.name:
                continue
            path = sql_planner.expand_required_tables([target_table.name, table.name], relationships)
            if table.name not in path or len(path) < 2:
                continue
            columns = self._group_by_columns_for_table(question, table, column_prefix=table.name)
            if columns:
                group_by.extend(columns)
                if table.name not in related_tables:
                    related_tables.append(table.name)
        return list(dict.fromkeys(group_by)), related_tables

    def _numeric_aggregation_for_table(
        self,
        question: str,
        table: SemanticTable,
        column_prefix: str = "",
    ) -> Optional[dict[str, str]]:
        text = question.replace("‌", " ")
        function = None
        if any(term in text for term in ["میانگین", "متوسط"]):
            function = "AVG"
        elif any(term in text for term in ["مجموع", "جمع", "کل"]):
            function = "SUM"
        elif any(term in text for term in ["بیشترین", "بالاترین", "حداکثر"]):
            function = "MAX"
        elif any(term in text for term in ["کمترین", "پایین‌ترین", "پایین ترین", "حداقل"]):
            function = "MIN"
        if not function:
            return None

        numeric_types = {"integer", "bigint", "numeric", "double precision", "real"}
        candidates = []
        for column in table.columns:
            if column.data_type not in numeric_types or column.name.endswith("_id"):
                continue
            labels = [
                (label or "").replace("‌", " ").strip()
                for label in [column.name, *column.aliases]
                if label and len((label or "").replace("‌", " ").strip()) >= 2
            ]
            if any(label in text for label in labels):
                column_name = f"{column_prefix}.{column.name}" if column_prefix else column.name
                candidates.append({"function": function, "column": column_name})
        if len(candidates) == 1:
            return candidates[0]
        return None

    def _ranking_order_for_table(
        self,
        question: str,
        table: SemanticTable,
        column_prefix: str = "",
    ) -> Optional[str]:
        text = question.replace("‌", " ")
        direction = None
        if any(term in text for term in ["گران‌ترین", "گران ترین", "بیشترین", "بالاترین"]):
            direction = "DESC"
        elif any(term in text for term in ["ارزان‌ترین", "ارزان ترین", "کمترین", "پایین‌ترین", "پایین ترین"]):
            direction = "ASC"
        if not direction:
            return None

        numeric_types = {"integer", "bigint", "numeric", "double precision", "real"}
        candidates = []
        for column in table.columns:
            if column.data_type not in numeric_types or column.name.endswith("_id"):
                continue
            labels = [
                (label or "").replace("‌", " ").strip()
                for label in [column.name, *column.aliases]
                if label and len((label or "").replace("‌", " ").strip()) >= 2
            ]
            if any(label in text for label in labels):
                column_name = f"{column_prefix}.{column.name}" if column_prefix else column.name
                candidates.append(f"{column_name} {direction}")
        if not candidates:
            display_candidates = [
                column
                for column in table.columns
                if column.data_type in numeric_types
                and column.name != table.primary_key
                and column.name != "id"
                and not column.name.endswith("_id")
                and column.name in set(table.default_display_columns + table.profile_columns)
            ]
            if len(display_candidates) == 1:
                column_name = (
                    f"{column_prefix}.{display_candidates[0].name}"
                    if column_prefix
                    else display_candidates[0].name
                )
                candidates.append(f"{column_name} {direction}")
        if len(candidates) == 1:
            return candidates[0]
        return None

    def _related_numeric_aggregation_for_table(
        self,
        question: str,
        target_table: SemanticTable,
        catalog: SemanticCatalog,
    ) -> tuple[Optional[dict[str, str]], list[str]]:
        relationships = self._schema_relationships(catalog)
        candidates: list[tuple[str, dict[str, str]]] = []
        for table in catalog.tables:
            if table.name == target_table.name:
                continue
            path = sql_planner.expand_required_tables([target_table.name, table.name], relationships)
            if table.name not in path or len(path) < 2:
                continue
            aggregation = self._numeric_aggregation_for_table(question, table, column_prefix=table.name)
            if aggregation:
                candidates.append((table.name, aggregation))
        if len(candidates) == 1:
            return candidates[0][1], [candidates[0][0]]
        return None, []

    def _requested_columns_for_table(
        self,
        question: str,
        table: SemanticTable,
        column_prefix: str = "",
    ) -> list[str]:
        text = question.replace("‌", " ")
        if any(term in text for term in ["تعداد", "چند", "میانگین", "متوسط", "مجموع", "جمع"]):
            return []
        requested = []
        for column in table.columns:
            labels = [
                (label or "").replace("‌", " ").strip()
                for label in [column.name, *column.aliases]
                if label and len((label or "").replace("‌", " ").strip()) >= 2
            ]
            if any(label in text for label in labels):
                requested.append(f"{column_prefix}.{column.name}" if column_prefix else column.name)
        return list(dict.fromkeys(requested))

    def _requested_column_matches_for_table(
        self,
        question: str,
        table: SemanticTable,
        column_prefix: str = "",
    ) -> list[dict[str, str]]:
        text = question.replace("‌", " ")
        if any(term in text for term in ["تعداد", "چند", "میانگین", "متوسط", "مجموع", "جمع"]):
            return []
        matches = []
        for column in table.columns:
            labels = [
                (label or "").replace("‌", " ").strip()
                for label in [column.name, *column.aliases]
                if label and len((label or "").replace("‌", " ").strip()) >= 2
            ]
            for label in labels:
                if label in text:
                    matches.append(
                        {
                            "label": label,
                            "column": f"{column_prefix}.{column.name}" if column_prefix else column.name,
                            "table": column_prefix or table.name,
                        }
                    )
                    break
        return matches

    def _related_requested_columns_for_table(
        self,
        question: str,
        target_table: SemanticTable,
        catalog: SemanticCatalog,
    ) -> tuple[list[str], list[str]]:
        relationships = self._schema_relationships(catalog)
        base_matches = self._requested_column_matches_for_table(question, target_table)
        related_matches = []
        for table in catalog.tables:
            if table.name == target_table.name:
                continue
            path = sql_planner.expand_required_tables([target_table.name, table.name], relationships)
            if table.name not in path or len(path) < 2:
                continue
            related_matches.extend(self._requested_column_matches_for_table(question, table, column_prefix=table.name))

        by_label: dict[str, list[dict[str, str]]] = {}
        for match in [*base_matches, *related_matches]:
            by_label.setdefault(match["label"], []).append(match)
        ambiguous = [
            {"label": label, "columns": [item["column"] for item in items]}
            for label, items in by_label.items()
            if len({item["column"] for item in items}) > 1
        ]
        if ambiguous:
            self._last_related_ambiguity = {
                "type": "requested_column",
                "items": ambiguous,
            }
            ambiguous_columns = {column for item in ambiguous for column in item["columns"]}
        else:
            ambiguous_columns = set()

        requested = []
        related_tables = []
        for match in related_matches:
            if match["column"] in ambiguous_columns:
                continue
            requested.append(match["column"])
            if match["table"] not in related_tables:
                related_tables.append(match["table"])
        return list(dict.fromkeys(requested)), related_tables

    def _has_filter(self, filters: list[dict[str, str]], column: str) -> bool:
        return any(item["column"] == column for item in filters)

    def _parse_number_phrase(self, value: str) -> Optional[int]:
        normalized = (
            value.replace("‌", " ")
            .replace(",", "")
            .replace("،", "")
            .replace("٫", ".")
            .strip()
        )
        translation = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
        normalized = normalized.translate(translation)
        match = re.search(r"\d+(?:\.\d+)?", normalized)
        if not match:
            return None
        number = float(match.group(0))
        if "میلیارد" in normalized:
            number *= 1_000_000_000
        elif "میلیون" in normalized:
            number *= 1_000_000
        elif "هزار" in normalized:
            number *= 1_000
        return int(number)

    def _temporal_filters_for_table(
        self,
        question: str,
        table: SemanticTable,
        existing_filters: list[dict[str, str]],
        column_prefix: str = "",
    ) -> list[dict[str, str]]:
        text = question.replace("‌", " ")
        translation = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
        normalized = text.translate(translation)
        year = None
        month = None
        year_match = re.search(r"سال\s+([0-9]{4})", normalized)
        if year_match:
            year = year_match.group(1)
        month_match = re.search(r"ماه\s+([0-9]{1,2})", normalized)
        if month_match and 1 <= int(month_match.group(1)) <= 12:
            month = month_match.group(1)
        relative_operator = None
        relative_value = ""
        recent_days_match = re.search(r"([0-9]{1,3})\s+روز\s+(?:اخیر|گذشته|قبل)", normalized)
        if "امروز" in normalized:
            relative_operator = "DATE="
            relative_value = "CURRENT_DATE"
        elif "امسال" in normalized:
            relative_operator = "YEAR_CURRENT"
        elif "ماه قبل" in normalized or "ماه گذشته" in normalized:
            relative_operator = "PREVIOUS_MONTH"
        elif recent_days_match:
            relative_operator = "DAYS_AGO"
            relative_value = recent_days_match.group(1)
        if not year and not month and not relative_operator:
            return []

        existing_columns = {item["column"] for item in existing_filters}
        temporal_types = {"date", "timestamp", "timestamp without time zone", "timestamp with time zone"}
        candidates = []
        for column in table.columns:
            filter_column = f"{column_prefix}.{column.name}" if column_prefix else column.name
            if column.data_type not in temporal_types or column.name in existing_columns or filter_column in existing_columns:
                continue
            labels = [
                (label or "").replace("‌", " ").strip()
                for label in [column.name, *column.aliases]
                if label and len((label or "").replace("‌", " ").strip()) >= 2
            ]
            if any(label in text for label in labels) or column.name in {"created_at", "requested_at", "date"}:
                candidates.append(filter_column)
        if len(candidates) != 1:
            return []
        filters = []
        if year:
            filters.append({"column": candidates[0], "operator": "YEAR=", "value": year})
        if month:
            filters.append({"column": candidates[0], "operator": "MONTH=", "value": month})
        if relative_operator:
            filters.append({"column": candidates[0], "operator": relative_operator, "value": relative_value})
        return filters

    def _numeric_filters_for_table(
        self,
        question: str,
        table: SemanticTable,
        existing_filters: list[dict[str, str]],
        column_prefix: str = "",
    ) -> list[dict[str, str]]:
        text = question.replace("‌", " ")
        existing_columns = {item["column"] for item in existing_filters}
        filters = []
        numeric_types = {"integer", "bigint", "numeric", "double precision", "real"}
        operator_terms = [
            (">=", ["حداقل", "دست کم", "دست‌کم", "بیشتر یا مساوی", "بالاتر یا مساوی"]),
            ("<=", ["حداکثر", "کمتر یا مساوی", "پایین تر یا مساوی", "پایین‌تر یا مساوی"]),
            (">", ["بیشتر از", "بالاتر از", "بالای", "بیش از"]),
            ("<", ["کمتر از", "پایین تر از", "پایین‌تر از", "زیر"]),
        ]
        stop_pattern = r"(.+?)(?:\s+(?:و|در|استان|شهر|با|که|را|رو)\s+|$)"
        for column in table.columns:
            filter_column = f"{column_prefix}.{column.name}" if column_prefix else column.name
            if (
                column.name in existing_columns
                or filter_column in existing_columns
                or column.data_type not in numeric_types
            ):
                continue
            labels = [
                (label or "").replace("‌", " ").strip()
                for label in [column.name, *column.aliases]
                if label and len((label or "").replace("‌", " ").strip()) >= 2
            ]
            if not labels:
                continue
            for operator, terms in operator_terms:
                matched_column = False
                for label in labels:
                    for term in terms:
                        patterns = [
                            rf"{re.escape(label)}\s+{re.escape(term)}\s+{stop_pattern}",
                            rf"{re.escape(term)}\s+{stop_pattern}\s+{re.escape(label)}",
                        ]
                        for pattern in patterns:
                            match = re.search(pattern, text)
                            if not match:
                                continue
                            number = self._parse_number_phrase(match.group(1))
                            if number is not None:
                                filters.append({"column": filter_column, "operator": operator, "value": str(number)})
                                matched_column = True
                                break
                        if matched_column:
                            break
                    if matched_column:
                        break
                if matched_column:
                    break
        return self._dedupe_filters(filters)

    def _value_driven_filters_for_table(
        self,
        question: str,
        table: SemanticTable,
        existing_filters: list[dict[str, str]],
    ) -> list[dict[str, str]]:
        text = question.replace("‌", " ")
        if "با " not in text:
            return []

        existing_columns = {item["column"] for item in existing_filters}
        discovery = self._load_discovery_snapshot()
        if not discovery:
            return []
        discovered_table = next((item for item in discovery.tables if item.name == table.name), None)
        if not discovered_table:
            return []

        candidates = []
        existing_values = {
            str(item["value"]).replace("‌", " ").strip()
            for item in existing_filters
            if item.get("value") not in (None, "")
        }
        indexed_matches = value_index_service.search(
            question,
            tenant_id=self.settings.tenant_id,
            table=table.name,
        )
        for match in indexed_matches:
            if match.column in existing_columns or match.value in existing_values:
                continue
            candidates.append(
                (
                    match.column,
                    match.value,
                    len(self._normalize_text(match.value)),
                    match.count,
                )
            )

        for column in discovered_table.columns:
            if column.name in existing_columns or column.is_primary_key or column.name.endswith("_id"):
                continue
            for sample in column.sample_values:
                value = (sample.value or "").replace("‌", " ").strip()
                if len(value) < 2:
                    continue
                if value in existing_values:
                    continue
                if re.search(rf"(?<!\S){re.escape(value)}(?!\S)", text):
                    candidates.append((column.name, sample.value or value, len(value), sample.count))

        if not candidates:
            return []
        candidates.sort(key=lambda item: (item[2], item[3]), reverse=True)
        best_column, best_value, _, _ = candidates[0]
        tied_columns = {column for column, value, score, count in candidates if value == best_value}
        if len(tied_columns) > 1:
            return []
        return [{"column": best_column, "operator": "=", "value": best_value}]

    def _ambiguous_value_filter_for_table(self, question: str, table: SemanticTable) -> Optional[dict[str, list[str] | str]]:
        text = question.replace("‌", " ")
        if "با " not in text:
            return None

        discovery = self._load_discovery_snapshot()
        if not discovery:
            return None

        matches = self._sample_value_mentions_for_table(question, table, discovery)
        if not matches:
            return None

        by_value: dict[str, set[str]] = {}
        for column_name, value, _, _ in matches:
            by_value.setdefault(value, set()).add(column_name)

        ambiguous_items = [(value, sorted(columns)) for value, columns in by_value.items() if len(columns) > 1]
        if not ambiguous_items:
            return None

        label_text = self._normalize_text(text)
        all_labels = []
        for column in table.columns:
            all_labels.extend([column.name, *column.aliases])
        if any(self._normalize_text(label or "") in label_text for label in all_labels if label and len(label) >= 2):
            return None

        value, columns = ambiguous_items[0]
        return {"value": value, "columns": columns}

    def _training_request_filters(self, question: str) -> list[dict[str, str]]:
        filters: list[dict[str, str]] = []
        text = question.replace("‌", " ")
        mappings = [
            ("status", "approved", ["تایید شده", "تأیید شده", "مصوب", "قبول شده"]),
            ("status", "pending", ["در انتظار", "منتظر بررسی", "بررسی نشده"]),
            ("status", "rejected", ["رد شده", "ردشده", "مردود"]),
            ("status", "active", ["فعال", "باز", "در حال رسیدگی"]),
            ("priority", "high", ["اولویت بالا", "فوری", "مهم"]),
            ("priority", "normal", ["اولویت عادی", "اولویت معمولی", "عادی"]),
            ("priority", "low", ["کم اولویت", "کم‌اولویت", "اولویت پایین"]),
            ("request_type", "کارگاه هوش مصنوعی", ["کارگاه هوش مصنوعی", "هوش مصنوعی"]),
            ("request_type", "دوره ضمن خدمت معلمان", ["ضمن خدمت", "ضمن خدمت معلمان"]),
            ("request_type", "دوره امور مالی", ["امور مالی", "مالی"]),
            ("request_type", "آموزش ایمنی مدارس", ["ایمنی مدارس", "ایمنی"]),
            ("request_type", "دوره مدیریت مدرسه", ["مدیریت مدرسه", "مدیریت مدارس"]),
            ("request_type", "آموزش مشاوره دانش‌آموزی", ["مشاوره دانش آموزی", "مشاوره دانش‌آموزی", "مشاوره"]),
            ("assigned_unit", "مرکز فناوری آموزشی", ["مرکز فناوری آموزشی"]),
            ("assigned_unit", "اداره آموزش نیروی انسانی", ["اداره آموزش نیروی انسانی", "نیروی انسانی"]),
            ("assigned_unit", "اداره مالی", ["اداره مالی"]),
            ("assigned_unit", "اداره سلامت و ایمنی", ["اداره سلامت و ایمنی"]),
            ("assigned_unit", "اداره آموزش مدیران", ["اداره آموزش مدیران"]),
        ]
        for column, value, needles in mappings:
            if any(needle in text for needle in needles):
                filters.append({"column": column, "operator": "=", "value": value})

        requester_role = self._extract_value_after_any(
            text,
            ["requester_role", "پست", "سمت", "نقش", "نقش درخواست‌دهنده", "سمت درخواست‌دهنده"],
            ["مدیر مدرسه", "معاون آموزشی", "کارشناس منطقه", "کارمند اداری", "معلم", "کارشناس آموزش", "معاون پرورشی"],
        )
        if requester_role:
            filters.append({"column": "requester_role", "operator": "=", "value": requester_role})

        for city in ["تهران", "ری", "اصفهان", "کاشان", "مشهد", "شیراز", "ساری", "اهواز", "کرمان", "رشت", "زاهدان"]:
            if f"شهر {city}" in text:
                filters.append({"column": "city", "operator": "=", "value": city})

        for province in ["تهران", "اصفهان", "خراسان رضوی", "خوزستان", "فارس", "مازندران", "کرمان", "گیلان", "سیستان و بلوچستان"]:
            if f"استان {province}" in text:
                filters.append({"column": "province", "operator": "=", "value": province})
            elif province in text and not self._has_filter(filters, "city"):
                filters.append({"column": "province", "operator": "=", "value": province})

        table = load_tenant_semantic_catalog(self.settings.tenant_id).table("demo_training_requests")
        if table:
            filters.extend(self._semantic_filters_for_table(question, table))
            filters.extend(self._labeled_value_filters_for_table(question, table, filters))
            filters.extend(self._numeric_filters_for_table(question, table, filters))
            filters.extend(self._value_driven_filters_for_table(question, table, filters))
        return self._dedupe_filters(filters)

    def _training_request_plan(
        self,
        question: str,
        catalog: SemanticCatalog,
        extra_filters: Optional[list[dict[str, str]]] = None,
    ) -> Optional[SQLPlan]:
        if not self._is_training_request_question(question, catalog):
            return None
        text = question.replace("‌", " ")
        filters = self._training_request_filters(question)
        for item in extra_filters or []:
            if not self._has_filter(filters, item.get("column", "")):
                filters.append(item)
        table = catalog.table("demo_training_requests")
        default_columns = table.default_display_columns if table else [
            "requester_name",
            "request_type",
            "province",
            "priority",
            "status",
            "estimated_cost",
        ]
        if "میانگین" in text and "هزینه" in text:
            return SQLPlan(
                required_tables=["demo_training_requests"],
                selected_columns=["TRAINING_REQUEST_COST_AVG"],
                filters=filters,
                aggregations=[{"function": "AVG", "column": "demo_training_requests.estimated_cost"}],
            )
        if ("مجموع" in text or "جمع" in text) and "هزینه" in text:
            return SQLPlan(
                required_tables=["demo_training_requests"],
                selected_columns=["TRAINING_REQUEST_COST_SUM"],
                filters=filters,
                aggregations=[{"function": "SUM", "column": "demo_training_requests.estimated_cost"}],
            )
        if "گران ترین" in text or "گران‌ترین" in text or "بیشترین هزینه" in text:
            return SQLPlan(
                required_tables=["demo_training_requests"],
                selected_columns=["TRAINING_REQUEST_RANKED_COST"],
                filters=filters,
                order_by="estimated_cost DESC",
                limit=1,
            )
        if "ارزان ترین" in text or "ارزان‌ترین" in text or "کمترین هزینه" in text:
            return SQLPlan(
                required_tables=["demo_training_requests"],
                selected_columns=["TRAINING_REQUEST_RANKED_COST"],
                filters=filters,
                order_by="estimated_cost ASC",
                limit=1,
            )
        if "تعداد" in text or "چند" in text:
            return SQLPlan(
                required_tables=["demo_training_requests"],
                selected_columns=["TRAINING_REQUEST_COUNT"],
                filters=filters,
                aggregations=[{"function": "COUNT", "column": "demo_training_requests.id"}],
            )
        return SQLPlan(
            required_tables=["demo_training_requests"],
            selected_columns=["TRAINING_REQUEST_LIST", *default_columns],
            filters=filters,
        )

    def _semantic_table_plan(
        self,
        question: str,
        catalog: SemanticCatalog,
        preferred_table: Optional[str] = None,
        grounded_filters: Optional[list[dict[str, str]]] = None,
    ) -> Optional[SQLPlan]:
        target_table = None
        if preferred_table:
            target_table = catalog.table(preferred_table)
        if not target_table:
            target_table = self._semantic_target_table(question, catalog)
        if not target_table:
            target_table = self._semantic_target_table_by_labeled_sample_values(question, catalog)
        if not target_table:
            target_table = self._semantic_target_table_by_sample_values(question, catalog)
        if not target_table and self._is_training_request_question(question, catalog):
            target_table = catalog.table("demo_training_requests")
        if not target_table:
            return None
        if target_table.name == "demo_training_requests":
            return self._training_request_plan(
                question,
                catalog,
                extra_filters=grounded_filters,
            )

        text = self._normalize_text(question)
        filters = self._semantic_filters_for_table(question, target_table)
        filters.extend(self._labeled_value_filters_for_table(question, target_table, filters))
        filters.extend(self._numeric_filters_for_table(question, target_table, filters))
        filters.extend(self._temporal_filters_for_table(question, target_table, filters))
        filters.extend(self._value_driven_filters_for_table(question, target_table, filters))
        related_filters, related_tables = self._related_labeled_value_filters_for_table(question, target_table, catalog, filters)
        filters.extend(related_filters)
        related_numeric_filters, related_numeric_tables = self._related_numeric_filters_for_table(question, target_table, catalog, filters)
        filters.extend(related_numeric_filters)
        for table_name in related_numeric_tables:
            if table_name not in related_tables:
                related_tables.append(table_name)
        group_by = self._group_by_columns_for_table(question, target_table)
        related_group_by, related_group_tables = self._related_group_by_columns_for_table(question, target_table, catalog)
        group_by.extend(related_group_by)
        for table_name in related_group_tables:
            if table_name not in related_tables:
                related_tables.append(table_name)
        aggregation = self._numeric_aggregation_for_table(question, target_table)
        related_aggregation, related_aggregation_tables = self._related_numeric_aggregation_for_table(question, target_table, catalog)
        if not aggregation and related_aggregation:
            aggregation = related_aggregation
        for table_name in related_aggregation_tables:
            if table_name not in related_tables:
                related_tables.append(table_name)
        ranking_order = self._ranking_order_for_table(question, target_table)
        requested_columns = self._requested_columns_for_table(question, target_table)
        related_requested_columns, related_requested_tables = self._related_requested_columns_for_table(question, target_table, catalog)
        requested_columns.extend(related_requested_columns)
        if self._last_related_ambiguity and self._last_related_ambiguity.get("type") == "requested_column":
            ambiguous_columns = {
                column
                for item in self._last_related_ambiguity.get("items", [])
                for column in item.get("columns", [])
            }
            requested_columns = [column for column in requested_columns if column not in ambiguous_columns]
        for table_name in related_requested_tables:
            if table_name not in related_tables:
                related_tables.append(table_name)
        relationships = self._schema_relationships(catalog)
        required_tables = sql_planner.expand_required_tables([target_table.name, *related_tables], relationships)
        joins = sql_planner.detect_joins(required_tables, relationships)
        if ranking_order and any(term in text for term in ["کدام", "نشان بده", "نمایش بده", "اطلاعات"]):
            return SQLPlan(
                required_tables=required_tables,
                joins=joins,
                selected_columns=["GENERIC_TABLE_LIST", *(list(dict.fromkeys(requested_columns)) or target_table.default_display_columns)],
                filters=filters,
                order_by=ranking_order,
                limit=1,
            )
        if aggregation:
            return SQLPlan(
                required_tables=required_tables,
                joins=joins,
                selected_columns=["GENERIC_TABLE_AGGREGATE"],
                filters=filters,
                aggregations=[aggregation],
                group_by=list(dict.fromkeys(group_by)),
            )
        if "تعداد" in text or "چند" in text:
            return SQLPlan(
                required_tables=required_tables,
                joins=joins,
                selected_columns=["GENERIC_TABLE_COUNT"],
                filters=filters,
                aggregations=[{"function": "COUNT", "column": f"{target_table.name}.{target_table.primary_key}"}],
                group_by=list(dict.fromkeys(group_by)),
            )
        return SQLPlan(
            required_tables=required_tables,
            joins=joins,
            selected_columns=["GENERIC_TABLE_LIST", *(list(dict.fromkeys(requested_columns)) or target_table.default_display_columns)],
            filters=filters,
        )

    def _select_report_id(self, intent, report_id: str) -> str:
        if intent.requested_entity == "salary":
            return "salary_summary"
        if intent.requested_entity == "ranking":
            return "ranking_summary"
        if intent.requested_entity == "school" and intent.grouping:
            return "school_statistics"
        if intent.requested_entity == "school":
            return "school_statistics"
        if intent.requested_entity == "student":
            return "student_list"
        if intent.requested_entity == "employee":
            if intent.aggregation == "COUNT":
                return "employee_statistics"
            return "employee_list"
        if intent.requested_entity == "organization":
            return "organization_structure"
        if intent.requested_entity == "retirement":
            return "employee_list"
        return report_id

    def _fallback_group(self, intent, semantic_table_name: str = "") -> tuple[str, str]:
        if semantic_table_name:
            group_id = "training_request" if semantic_table_name == "demo_training_requests" else semantic_table_name
            return group_id, group_id
        if intent.requested_entity == "salary":
            return "salary", "salary"
        if intent.requested_entity in {"employee", "retirement"}:
            return "employee", "employee"
        if intent.requested_entity in {"student", "school"}:
            return "student", "student"
        if intent.requested_entity == "organization":
            return "organization", "organization"
        return "", ""

    def _fallback_report(self, intent, tenant_id: str, semantic_table_name: str = "") -> tuple[str, str, Optional[Report]]:
        if semantic_table_name:
            report_id = f"semantic_table_{semantic_table_name}"
            report_name = "درخواست‌های آموزشی" if semantic_table_name == "demo_training_requests" else semantic_table_name
            return report_id, report_name, None
        report_id = self._select_report_id(intent, "")
        if not report_id:
            return "", "", None
        report_obj = self._get_report(tenant_id, report_id)
        report_name = report_obj.name if report_obj else report_id
        return report_id, report_name, report_obj

    def _schema_relationships(self, catalog: SemanticCatalog) -> list:
        return [
            RelationshipInfo(
                source_table=join.from_table,
                source_column=join.from_column,
                target_table=join.to_table,
                target_column=join.to_column,
                relationship_type=join.cardinality,
            )
            for join in catalog.joins
        ]

    def _scope_schema(self, schema: DatabaseSchema, report: Optional[Report]) -> DatabaseSchema:
        if not report:
            return schema

        allowed = {report.linked_table}
        if report.sql_hints:
            for join in report.sql_hints.preferred_joins:
                for token in join.replace("=", " ").split():
                    if "." in token:
                        allowed.add(token.split(".")[0])

        return DatabaseSchema(
            tables=[table for table in schema.tables if table.name in allowed],
            relationships=[
                rel for rel in schema.relationships
                if rel.source_table in allowed and rel.target_table in allowed
            ],
            foreign_keys=[
                fk for fk in schema.foreign_keys
                if fk.table_name in allowed and fk.foreign_table_name in allowed
            ],
        )

    def _apply_intent_to_plan(
        self,
        plan: SQLPlan,
        intent,
        report: Optional[Report],
        schema: DatabaseSchema,
        semantic_catalog: Optional[SemanticCatalog] = None,
    ) -> SQLPlan:
        active_catalog = semantic_catalog or load_tenant_semantic_catalog(self.settings.tenant_id)
        if report and report.linked_table not in plan.required_tables:
            plan.required_tables.insert(0, report.linked_table)

        if intent.requested_entity == "salary":
            needs_location_join = bool(intent.province or intent.city or intent.province_values or intent.city_values)
            plan.required_tables = ["salary_items", "employees", "organization_units"] if needs_location_join else ["salary_items", "employees"]
            plan.joins = [{
                "from_table": "salary_items",
                "from_column": "employee_id",
                "to_table": "employees",
                "to_column": "id",
            }]
            if needs_location_join:
                plan.joins.append({
                    "from_table": "employees",
                    "from_column": "organization_unit_id",
                    "to_table": "organization_units",
                    "to_column": "id",
                })
            if intent.sorting and intent.limit == 1:
                plan.selected_columns = ["SALARY_TOTAL_BY_EMPLOYEE"]
                plan.aggregations = [{"function": "SUM", "column": "salary_items.net_salary"}]
                plan.order_by = f"total_salary {intent.sorting.direction}"
                plan.limit = 1
            elif intent.aggregation in {"COUNT", "SUM", "AVG"}:
                function = intent.aggregation
                salary_columns = {
                    "base_salary", "allowances", "deductions", "net_salary",
                }
                requested_metric = next(
                    (column for column in intent.requested_columns if column in salary_columns),
                    "net_salary",
                )
                metric_column = "salary_items.id" if function == "COUNT" else f"salary_items.{requested_metric}"
                plan.selected_columns = ["SALARY_AGGREGATE"]
                plan.aggregations = [{"function": function, "column": metric_column}]
                plan.group_by = list(intent.grouping)
                plan.order_by = None
                plan.limit = None
            elif {"base_salary", "net_salary"}.issubset(set(intent.requested_columns)):
                plan.selected_columns = ["SALARY_COMPARISON"]
                plan.aggregations = [
                    {"function": "AVG", "column": "salary_items.base_salary"},
                    {"function": "AVG", "column": "salary_items.net_salary"},
                ]
                plan.group_by = []
                plan.order_by = None
                plan.limit = None
            else:
                requested = list(intent.requested_columns) or [
                    "year", "month", "base_salary", "allowances", "deductions", "net_salary",
                ]
                plan.selected_columns = ["SALARY_LIST", *requested]
                plan.aggregations = []
                plan.group_by = []
                plan.order_by = None
                plan.limit = None
            plan.filters = []
            if intent.date_range:
                if intent.date_range.get("year"):
                    plan.filters.append({"column": "year", "operator": "=", "value": str(intent.date_range["year"])})
                if intent.date_range.get("month"):
                    plan.filters.append({"column": "month", "operator": "=", "value": str(intent.date_range["month"])})
            if intent.national_id:
                plan.filters.append({"column": "national_id", "operator": "=", "value": intent.national_id})
            if intent.first_name:
                plan.filters.append({"column": "first_name", "operator": "=", "value": intent.first_name})
            if intent.last_name:
                plan.filters.append({"column": "last_name", "operator": "=", "value": intent.last_name})
            if intent.status:
                plan.filters.append({"column": "status", "operator": "=", "value": intent.status})
            if intent.position:
                plan.filters.append({"column": "position", "operator": "=", "value": intent.position})
            if intent.hire_year:
                plan.filters.append({"column": "hire_year", "operator": "=", "value": str(intent.hire_year)})
            if intent.province:
                plan.filters.append({"column": "province", "operator": "=", "value": intent.province})
            if intent.city:
                plan.filters.append({"column": "city", "operator": "=", "value": intent.city})

        if intent.requested_entity == "organization":
            plan.required_tables = ["organization_units"]
            if intent.named_organization_unit:
                plan.selected_columns = ["ORGANIZATION_UNIT_BY_NAME"]
                plan.filters = [{"column": "name", "operator": "=", "value": intent.named_organization_unit}]
                plan.aggregations = []
            else:
                plan.selected_columns = ["province", "COUNT(*) AS unit_count"]
                plan.aggregations = [{"function": "COUNT", "column": "*"}]
                plan.group_by = ["province"]
                plan.order_by = "unit_count DESC"
            plan.joins = []

        if intent.requested_entity == "retirement":
            plan.required_tables = ["retirement_records", "employees"]
            if intent.ranking_metric == "pension_amount" and intent.sorting and intent.limit == 1:
                plan.selected_columns = ["RETIREMENT_PENSION_AMOUNT_BY_EMPLOYEE"]
                plan.order_by = f"retirement_records.pension_amount {intent.sorting.direction}"
                plan.limit = 1
            else:
                plan.selected_columns = [
                    "retirement_records.employee_id",
                    "retirement_records.years_of_service",
                    "retirement_records.pension_amount",
                    "retirement_records.retirement_date",
                ]
            plan.joins = [{
                "from_table": "retirement_records",
                "from_column": "employee_id",
                "to_table": "employees",
                "to_column": "id",
            }]

        if intent.requested_entity == "student":
            if intent.national_id:
                student_table = active_catalog.table("students")
                profile_columns = student_table.profile_columns if student_table else []
                selected_columns = list(intent.requested_columns) if intent.requested_columns and not intent.wants_full_profile else list(profile_columns)
                if not selected_columns:
                    selected_columns = ["first_name", "last_name", "national_id", "grade", "status"]
                if "national_id" not in selected_columns:
                    selected_columns.insert(0, "national_id")
                if "last_name" not in selected_columns:
                    selected_columns.insert(0, "last_name")
                if "first_name" not in selected_columns:
                    selected_columns.insert(0, "first_name")
                if intent.wants_school_name:
                    selected_columns = [
                        column for column in selected_columns if column != "school_id"
                    ]
                    selected_columns.append("school_name")
                    plan.required_tables = ["students", "schools"]
                    plan.joins = [{
                        "from_table": "students",
                        "from_column": "school_id",
                        "to_table": "schools",
                        "to_column": "id",
                    }]
                else:
                    plan.required_tables = ["students"]
                plan.selected_columns = ["STUDENT_BY_NATIONAL_ID", *selected_columns]
                plan.filters = [{"column": "national_id", "operator": "=", "value": intent.national_id}]
            elif intent.named_school:
                plan.required_tables = ["students", "schools"]
                plan.selected_columns = ["STUDENT_COUNT_BY_SCHOOL_NAME"] if intent.aggregation == "COUNT" else ["STUDENT_LIST_BY_SCHOOL_NAME"]
                if intent.aggregation == "COUNT":
                    plan.aggregations = [{"function": "COUNT", "column": "students.id"}]
                plan.filters = [{"column": "school_name", "operator": "=", "value": intent.named_school}]
                if intent.first_name:
                    plan.filters.append({"column": "first_name", "operator": "=", "value": intent.first_name})
                if intent.last_name:
                    plan.filters.append({"column": "last_name", "operator": "=", "value": intent.last_name})
                if intent.grade:
                    plan.filters.append({"column": "grade", "operator": "=", "value": intent.grade})
                if intent.enrollment_year:
                    plan.filters.append({"column": "enrollment_year", "operator": "=", "value": str(intent.enrollment_year)})
                if intent.status:
                    plan.filters.append({"column": "status", "operator": "=", "value": intent.status})
                plan.joins = [
                    {
                        "from_table": "students",
                        "from_column": "school_id",
                        "to_table": "schools",
                        "to_column": "id",
                    }
                ]
            elif intent.aggregation == "COUNT" and intent.grouping and intent.grouping[0] in {"province", "city"}:
                dimension = intent.grouping[0]
                plan.required_tables = ["students", "schools", "organization_units"]
                plan.selected_columns = [f"STUDENT_COUNT_GROUPED_BY_{dimension.upper()}"]
                plan.aggregations = [{"function": "COUNT", "column": "students.id"}]
                plan.group_by = [dimension]
                if intent.sorting:
                    plan.order_by = f"student_count {intent.sorting.direction}"
                plan.limit = intent.limit
                plan.filters = []
                if intent.province_values:
                    plan.filters.append({"column": "province_values", "operator": "IN", "value": "|".join(intent.province_values)})
                if intent.city_values:
                    plan.filters.append({"column": "city_values", "operator": "IN", "value": "|".join(intent.city_values)})
                if intent.status:
                    plan.filters.append({"column": "status", "operator": "=", "value": intent.status})
                plan.joins = [
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
                ]
            elif intent.province:
                plan.required_tables = ["students", "schools", "organization_units"]
                plan.selected_columns = ["STUDENT_COUNT_BY_PROVINCE"] if intent.aggregation == "COUNT" else ["STUDENT_LIST_BY_PROVINCE"]
                if intent.aggregation == "COUNT":
                    plan.aggregations = [{"function": "COUNT", "column": "students.id"}]
                plan.filters = [{"column": "province", "operator": "=", "value": intent.province}]
                if intent.named_student:
                    plan.filters.append({"column": "first_name", "operator": "=", "value": intent.named_student})
                if intent.last_name:
                    plan.filters.append({"column": "last_name", "operator": "=", "value": intent.last_name})
                if intent.grade:
                    plan.filters.append({"column": "grade", "operator": "=", "value": intent.grade})
                if intent.enrollment_year:
                    plan.filters.append({"column": "enrollment_year", "operator": "=", "value": str(intent.enrollment_year)})
                if intent.status:
                    plan.filters.append({"column": "status", "operator": "=", "value": intent.status})
                plan.joins = [
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
                ]
            elif intent.city:
                plan.required_tables = ["students", "schools", "organization_units"]
                plan.selected_columns = ["STUDENT_COUNT_BY_CITY"] if intent.aggregation == "COUNT" else ["STUDENT_LIST_BY_CITY"]
                if intent.aggregation == "COUNT":
                    plan.aggregations = [{"function": "COUNT", "column": "students.id"}]
                plan.filters = [{"column": "city", "operator": "=", "value": intent.city}]
                if intent.named_student:
                    plan.filters.append({"column": "first_name", "operator": "=", "value": intent.named_student})
                if intent.last_name:
                    plan.filters.append({"column": "last_name", "operator": "=", "value": intent.last_name})
                if intent.grade:
                    plan.filters.append({"column": "grade", "operator": "=", "value": intent.grade})
                if intent.enrollment_year:
                    plan.filters.append({"column": "enrollment_year", "operator": "=", "value": str(intent.enrollment_year)})
                if intent.status:
                    plan.filters.append({"column": "status", "operator": "=", "value": intent.status})
                plan.joins = [
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
                ]
            elif intent.aggregation == "COUNT" and not (intent.first_name or intent.last_name):
                plan.required_tables = ["students"]
                plan.selected_columns = ["COUNT(students.id) AS total_students"]
                plan.aggregations = [{"function": "COUNT", "column": "students.id"}]
                plan.filters = []
                if intent.status:
                    plan.filters.append({"column": "status", "operator": "=", "value": intent.status})
                if intent.grade:
                    plan.filters.append({"column": "grade", "operator": "=", "value": intent.grade})
                if intent.enrollment_year:
                    plan.filters.append({"column": "enrollment_year", "operator": "=", "value": str(intent.enrollment_year)})
            elif intent.status:
                plan.required_tables = ["students"]
                plan.selected_columns = ["STUDENT_LIST_BY_STATUS"]
                plan.filters = [{"column": "status", "operator": "=", "value": intent.status}]
                if intent.grade:
                    plan.filters.append({"column": "grade", "operator": "=", "value": intent.grade})
                if intent.enrollment_year:
                    plan.filters.append({"column": "enrollment_year", "operator": "=", "value": str(intent.enrollment_year)})
            elif intent.first_name or intent.last_name:
                plan.required_tables = ["students", "schools"] if intent.wants_school_name else ["students"]
                if intent.aggregation == "COUNT":
                    plan.selected_columns = ["STUDENT_COUNT_BY_NAME"]
                    plan.aggregations = [{"function": "COUNT", "column": "students.id"}]
                else:
                    student_table = active_catalog.table("students")
                    if intent.wants_full_profile and student_table:
                        selected_columns = student_table.profile_columns
                    elif intent.requested_columns:
                        selected_columns = list(intent.requested_columns)
                    else:
                        selected_columns = student_table.default_display_columns if student_table else ["first_name", "last_name", "grade", "status"]
                    for required_column in ["first_name", "last_name"]:
                        if required_column not in selected_columns:
                            selected_columns.insert(0, required_column)
                    if intent.wants_school_name:
                        plan.selected_columns = ["STUDENT_SCHOOL_NAME_BY_NAME"]
                        plan.joins = [{
                            "from_table": "students",
                            "from_column": "school_id",
                            "to_table": "schools",
                            "to_column": "id",
                        }]
                    else:
                        plan.selected_columns = ["STUDENT_LIST_BY_NAME", *selected_columns]
                plan.filters = []
                if intent.first_name:
                    plan.filters.append({"column": "first_name", "operator": "=", "value": intent.first_name})
                if intent.last_name:
                    plan.filters.append({"column": "last_name", "operator": "=", "value": intent.last_name})
                if intent.grade:
                    plan.filters.append({"column": "grade", "operator": "=", "value": intent.grade})
                if intent.enrollment_year:
                    plan.filters.append({"column": "enrollment_year", "operator": "=", "value": str(intent.enrollment_year)})

        if intent.requested_entity == "school" and intent.aggregation == "COUNT" and intent.grouping and intent.grouping[0] in {"province", "city"}:
            dimension = intent.grouping[0]
            plan.required_tables = ["schools", "organization_units"]
            plan.selected_columns = [f"SCHOOL_COUNT_GROUPED_BY_{dimension.upper()}"]
            plan.aggregations = [{"function": "COUNT", "column": "schools.id"}]
            plan.group_by = [dimension]
            if intent.sorting:
                plan.order_by = f"school_count {intent.sorting.direction}"
            plan.limit = intent.limit
            plan.filters = []
            if intent.province_values:
                plan.filters.append({"column": "province_values", "operator": "IN", "value": "|".join(intent.province_values)})
            if intent.city_values:
                plan.filters.append({"column": "city_values", "operator": "IN", "value": "|".join(intent.city_values)})
            if intent.school_type:
                plan.filters.append({"column": "school_type", "operator": "=", "value": intent.school_type})
            if intent.capacity_min:
                plan.filters.append({"column": "capacity_min", "operator": ">=", "value": str(intent.capacity_min)})
            if intent.established_year:
                plan.filters.append({"column": "established_year", "operator": "=", "value": str(intent.established_year)})
            plan.joins = [{
                "from_table": "schools",
                "from_column": "organization_unit_id",
                "to_table": "organization_units",
                "to_column": "id",
            }]

        if intent.requested_entity == "school" and intent.province:
            plan.required_tables = ["schools", "organization_units"]
            plan.selected_columns = ["SCHOOL_COUNT_BY_PROVINCE"] if intent.aggregation == "COUNT" else ["SCHOOL_NAMES_BY_PROVINCE"]
            if intent.aggregation == "COUNT":
                plan.aggregations = [{"function": "COUNT", "column": "schools.id"}]
            plan.filters = [{"column": "province", "operator": "=", "value": intent.province}]
            if intent.school_type:
                plan.filters.append({"column": "school_type", "operator": "=", "value": intent.school_type})
            if intent.capacity_min:
                plan.filters.append({"column": "capacity_min", "operator": ">=", "value": str(intent.capacity_min)})
            if intent.established_year:
                plan.filters.append({"column": "established_year", "operator": "=", "value": str(intent.established_year)})
            plan.joins = [{
                "from_table": "schools",
                "from_column": "organization_unit_id",
                "to_table": "organization_units",
                "to_column": "id",
            }]

        if intent.requested_entity == "school" and intent.named_organization_unit:
            plan.required_tables = ["schools", "organization_units"]
            plan.selected_columns = ["SCHOOL_COUNT_BY_ORG_UNIT_NAME"] if intent.aggregation == "COUNT" else ["SCHOOL_NAMES_BY_ORG_UNIT_NAME"]
            if intent.aggregation == "COUNT":
                plan.aggregations = [{"function": "COUNT", "column": "schools.id"}]
            plan.filters = [{"column": "organization_unit_name", "operator": "=", "value": intent.named_organization_unit}]
            if intent.school_type:
                plan.filters.append({"column": "school_type", "operator": "=", "value": intent.school_type})
            if intent.capacity_min:
                plan.filters.append({"column": "capacity_min", "operator": ">=", "value": str(intent.capacity_min)})
            if intent.established_year:
                plan.filters.append({"column": "established_year", "operator": "=", "value": str(intent.established_year)})
            plan.joins = [{
                "from_table": "schools",
                "from_column": "organization_unit_id",
                "to_table": "organization_units",
                "to_column": "id",
            }]

        if intent.requested_entity == "school" and intent.city:
            plan.required_tables = ["schools", "organization_units"]
            plan.selected_columns = ["SCHOOL_COUNT_BY_CITY"] if intent.aggregation == "COUNT" else ["SCHOOL_NAMES_BY_CITY"]
            if intent.aggregation == "COUNT":
                plan.aggregations = [{"function": "COUNT", "column": "schools.id"}]
            plan.filters = [{"column": "city", "operator": "=", "value": intent.city}]
            if intent.school_type:
                plan.filters.append({"column": "school_type", "operator": "=", "value": intent.school_type})
            if intent.capacity_min:
                plan.filters.append({"column": "capacity_min", "operator": ">=", "value": str(intent.capacity_min)})
            if intent.established_year:
                plan.filters.append({"column": "established_year", "operator": "=", "value": str(intent.established_year)})
            plan.joins = [{
                "from_table": "schools",
                "from_column": "organization_unit_id",
                "to_table": "organization_units",
                "to_column": "id",
            }]

        if (
            intent.requested_entity == "school"
            and not intent.province
            and not intent.city
            and not intent.grouping
            and not intent.named_organization_unit
            and not intent.named_school
            and (intent.school_type or intent.capacity_min or intent.established_year)
        ):
            school_table = active_catalog.table("schools")
            selected_columns = school_table.default_display_columns if school_table else ["name", "school_type", "phone"]
            plan.required_tables = ["schools"]
            if intent.aggregation == "COUNT":
                plan.selected_columns = ["SCHOOL_COUNT_FILTERED"]
                plan.aggregations = [{"function": "COUNT", "column": "schools.id"}]
            else:
                plan.selected_columns = ["SCHOOL_LIST_FILTERED", *selected_columns]
            plan.filters = []
            if intent.school_type:
                plan.filters.append({"column": "school_type", "operator": "=", "value": intent.school_type})
            if intent.capacity_min:
                plan.filters.append({"column": "capacity_min", "operator": ">=", "value": str(intent.capacity_min)})
            if intent.established_year:
                plan.filters.append({"column": "established_year", "operator": "=", "value": str(intent.established_year)})

        if intent.requested_entity == "school" and intent.wants_phone and intent.named_school:
            plan.required_tables = ["schools"]
            plan.selected_columns = ["SCHOOL_PHONE_BY_NAME"]
            plan.filters = [{"column": "name", "operator": "ILIKE", "value": intent.named_school}]

        if intent.requested_entity == "school" and intent.named_school and not intent.wants_phone:
            school_table = active_catalog.table("schools")
            selected_columns = school_table.profile_columns if (intent.wants_full_profile and school_table) else (school_table.default_display_columns if school_table else ["name", "school_type", "phone"])
            plan.required_tables = ["schools"]
            plan.selected_columns = ["SCHOOL_BY_NAME", *selected_columns]
            plan.filters = [{"column": "name", "operator": "=", "value": intent.named_school}]
            if intent.school_type:
                plan.filters.append({"column": "school_type", "operator": "=", "value": intent.school_type})
            if intent.capacity_min:
                plan.filters.append({"column": "capacity_min", "operator": ">=", "value": str(intent.capacity_min)})
            if intent.established_year:
                plan.filters.append({"column": "established_year", "operator": "=", "value": str(intent.established_year)})

        if intent.requested_entity == "employee":
            if intent.national_id:
                employee_table = active_catalog.table("employees")
                profile_columns = employee_table.profile_columns if employee_table else []
                selected_columns = list(intent.requested_columns) if intent.requested_columns and not intent.wants_full_profile else list(profile_columns)
                if intent.wants_service_years:
                    selected_columns = ["first_name", "last_name", "national_id"]
                if not selected_columns:
                    selected_columns = ["first_name", "last_name", "national_id", "position", "status"]
                if "national_id" not in selected_columns:
                    selected_columns.insert(0, "national_id")
                if "last_name" not in selected_columns:
                    selected_columns.insert(0, "last_name")
                if "first_name" not in selected_columns:
                    selected_columns.insert(0, "first_name")
                plan.required_tables = ["employees", "retirement_records"] if intent.wants_service_years else ["employees"]
                template_name = "EMPLOYEE_PENSION_AMOUNT_BY_NATIONAL_ID" if intent.wants_service_years else "EMPLOYEE_BY_NATIONAL_ID"
                plan.selected_columns = [template_name, *selected_columns]
                plan.filters = [{"column": "national_id", "operator": "=", "value": intent.national_id}]
                if intent.wants_service_years:
                    plan.joins = [{
                        "from_table": "retirement_records",
                        "from_column": "employee_id",
                        "to_table": "employees",
                        "to_column": "id",
                    }]
            elif intent.province:
                plan.required_tables = ["employees", "organization_units"]
                if intent.aggregation == "COUNT":
                    plan.selected_columns = ["EMPLOYEE_COUNT_BY_PROVINCE"]
                    plan.aggregations = [{"function": "COUNT", "column": "employees.id"}]
                else:
                    employee_table = active_catalog.table("employees")
                    selected_columns = employee_table.default_display_columns if employee_table else ["first_name", "last_name", "position", "status"]
                    plan.selected_columns = ["EMPLOYEE_LIST_BY_PROVINCE", *selected_columns]
                plan.filters = [{"column": "province", "operator": "=", "value": intent.province}]
                if intent.first_name:
                    plan.filters.append({"column": "first_name", "operator": "=", "value": intent.first_name})
                if intent.last_name:
                    plan.filters.append({"column": "last_name", "operator": "=", "value": intent.last_name})
                if intent.status:
                    plan.filters.append({"column": "status", "operator": "=", "value": intent.status})
                if intent.position:
                    plan.filters.append({"column": "position", "operator": "=", "value": intent.position})
                if intent.hire_year:
                    plan.filters.append({"column": "hire_year", "operator": "=", "value": str(intent.hire_year)})
                plan.joins = [{
                    "from_table": "employees",
                    "from_column": "organization_unit_id",
                    "to_table": "organization_units",
                    "to_column": "id",
                }]
            elif intent.aggregation == "COUNT" and intent.grouping and intent.grouping[0] in {"province", "city"}:
                dimension = intent.grouping[0]
                plan.required_tables = ["employees", "organization_units"]
                plan.selected_columns = [f"EMPLOYEE_COUNT_GROUPED_BY_{dimension.upper()}"]
                plan.aggregations = [{"function": "COUNT", "column": "employees.id"}]
                plan.group_by = [dimension]
                if intent.sorting:
                    plan.order_by = f"employee_count {intent.sorting.direction}"
                plan.limit = intent.limit
                plan.filters = []
                if intent.province_values:
                    plan.filters.append({"column": "province_values", "operator": "IN", "value": "|".join(intent.province_values)})
                if intent.city_values:
                    plan.filters.append({"column": "city_values", "operator": "IN", "value": "|".join(intent.city_values)})
                if intent.status:
                    plan.filters.append({"column": "status", "operator": "=", "value": intent.status})
                if intent.position:
                    plan.filters.append({"column": "position", "operator": "=", "value": intent.position})
                if intent.hire_year:
                    plan.filters.append({"column": "hire_year", "operator": "=", "value": str(intent.hire_year)})
                plan.joins = [{
                    "from_table": "employees",
                    "from_column": "organization_unit_id",
                    "to_table": "organization_units",
                    "to_column": "id",
                }]
            elif intent.city:
                plan.required_tables = ["employees", "organization_units"]
                if intent.aggregation == "COUNT":
                    plan.selected_columns = ["EMPLOYEE_COUNT_BY_CITY"]
                    plan.aggregations = [{"function": "COUNT", "column": "employees.id"}]
                else:
                    employee_table = active_catalog.table("employees")
                    selected_columns = employee_table.default_display_columns if employee_table else ["first_name", "last_name", "position", "status"]
                    plan.selected_columns = ["EMPLOYEE_LIST_BY_CITY", *selected_columns]
                plan.filters = [{"column": "city", "operator": "=", "value": intent.city}]
                if intent.first_name:
                    plan.filters.append({"column": "first_name", "operator": "=", "value": intent.first_name})
                if intent.last_name:
                    plan.filters.append({"column": "last_name", "operator": "=", "value": intent.last_name})
                if intent.status:
                    plan.filters.append({"column": "status", "operator": "=", "value": intent.status})
                if intent.position:
                    plan.filters.append({"column": "position", "operator": "=", "value": intent.position})
                if intent.hire_year:
                    plan.filters.append({"column": "hire_year", "operator": "=", "value": str(intent.hire_year)})
                plan.joins = [{
                    "from_table": "employees",
                    "from_column": "organization_unit_id",
                    "to_table": "organization_units",
                    "to_column": "id",
                }]
            else:
                plan.required_tables = ["employees"]
                if intent.status:
                    if intent.aggregation == "COUNT":
                        plan.selected_columns = ["EMPLOYEE_COUNT_BY_STATUS"]
                        plan.aggregations = [{"function": "COUNT", "column": "employees.id"}]
                    else:
                        employee_table = active_catalog.table("employees")
                        selected_columns = employee_table.default_display_columns if employee_table else ["first_name", "last_name", "position", "status"]
                        plan.selected_columns = ["EMPLOYEE_LIST_BY_STATUS", *selected_columns]
                    plan.filters = [{"column": "status", "operator": "=", "value": intent.status}]
                    if intent.first_name:
                        plan.filters.append({"column": "first_name", "operator": "=", "value": intent.first_name})
                    if intent.last_name:
                        plan.filters.append({"column": "last_name", "operator": "=", "value": intent.last_name})
                    if intent.position:
                        plan.filters.append({"column": "position", "operator": "=", "value": intent.position})
                    if intent.hire_year:
                        plan.filters.append({"column": "hire_year", "operator": "=", "value": str(intent.hire_year)})
                elif intent.first_name or intent.last_name:
                    if intent.aggregation == "COUNT":
                        plan.selected_columns = ["EMPLOYEE_COUNT_BY_NAME"]
                        plan.aggregations = [{"function": "COUNT", "column": "employees.id"}]
                    else:
                        employee_table = active_catalog.table("employees")
                        if intent.wants_full_profile and employee_table:
                            selected_columns = employee_table.profile_columns
                        elif intent.requested_columns:
                            selected_columns = list(intent.requested_columns)
                        else:
                            selected_columns = employee_table.default_display_columns if employee_table else ["first_name", "last_name", "position", "status"]
                        for required_column in ["first_name", "last_name"]:
                            if required_column not in selected_columns:
                                selected_columns.insert(0, required_column)
                        plan.selected_columns = ["EMPLOYEE_LIST_BY_NAME", *selected_columns]
                    plan.filters = []
                    if intent.first_name:
                        plan.filters.append({"column": "first_name", "operator": "=", "value": intent.first_name})
                    if intent.last_name:
                        plan.filters.append({"column": "last_name", "operator": "=", "value": intent.last_name})
                    if intent.position:
                        plan.filters.append({"column": "position", "operator": "=", "value": intent.position})
                    if intent.hire_year:
                        plan.filters.append({"column": "hire_year", "operator": "=", "value": str(intent.hire_year)})
                elif intent.position or intent.hire_year:
                    if intent.aggregation == "COUNT":
                        plan.selected_columns = ["EMPLOYEE_COUNT_TOTAL"]
                        plan.aggregations = [{"function": "COUNT", "column": "employees.id"}]
                    else:
                        employee_table = active_catalog.table("employees")
                        selected_columns = list(intent.requested_columns) or (list(employee_table.default_display_columns) if employee_table else ["first_name", "last_name", "position", "status"])
                        plan.selected_columns = ["EMPLOYEE_LIST_FILTERED", *selected_columns]
                    plan.filters = []
                    if intent.position:
                        plan.filters.append({"column": "position", "operator": "=", "value": intent.position})
                    if intent.hire_year:
                        plan.filters.append({"column": "hire_year", "operator": "=", "value": str(intent.hire_year)})
                else:
                    plan.selected_columns = ["first_name", "last_name", "position", "status"]

        if intent.requested_entity == "ranking" and (intent.first_name or intent.last_name):
            plan.required_tables = ["ranking_requests", "employees"]
            ranking_columns = list(intent.requested_columns) or [
                "ranking_type", "current_rank", "requested_rank", "status"
            ]
            plan.selected_columns = ["RANKING_BY_EMPLOYEE_NAME", *ranking_columns]
            plan.filters = []
            if intent.first_name:
                plan.filters.append({"column": "first_name", "operator": "=", "value": intent.first_name})
            if intent.last_name:
                plan.filters.append({"column": "last_name", "operator": "=", "value": intent.last_name})

        if intent.semantic_metrics:
            metric_name = intent.semantic_metrics[0]
            metric = next((item for item in active_catalog.metrics if item.name == metric_name), None)
            if metric:
                plan.required_tables = list(dict.fromkeys([metric.table, *plan.required_tables]))
                plan.selected_columns = [f"SEMANTIC_METRIC:{metric.name}"]
                plan.aggregations = [{
                    "function": metric.aggregation or "VALUE",
                    "column": metric.expression,
                }]

        detected_joins = sql_planner.detect_joins(plan.required_tables, schema.relationships)
        if detected_joins:
            plan.joins = detected_joins
        return plan

    async def execute(self, request: PipelineRequest) -> PipelineResponse:
        tracer = PipelineTracer()
        self._last_related_ambiguity = None
        tenant_id = request.tenant_id or self.settings.tenant_id

        # Clarification resume (roadmap Change 5): a follow-up in the same
        # session continues the ORIGINAL request with the answer appended.
        resumed_clarification = None
        if request.session_id:
            pending = clarification_store.pop(request.session_id)
            if pending is not None:
                resumed_clarification = pending
                request = request.model_copy(
                    update={"question": f"{pending.original_question} {request.question}".strip()}
                )
                tracer.add_step(
                    "clarification_resume",
                    "success",
                    0.0,
                    data={
                        # Audit: which interpretation the user selected.
                        "session_id": pending.session_id,
                        "original_question": pending.original_question,
                        "user_answer": request.question.split(pending.original_question)[-1].strip(),
                        "candidate_options": pending.candidates,
                    },
                )

        semantic_snapshot: SemanticSnapshot = semantic_snapshot_provider.capture(tenant_id)
        active_catalog = semantic_snapshot.catalog
        start_time = time.time()
        question_text = self._normalize_text(request.question)
        complex_question = any(term in question_text for term in [
            "مقایسه", "بر اساس", "به تفکیک", "در هر", "روند", "ماه اخیر",
            "بیش از", "کمتر از", "بالاتر از", "پایین تر از", "پایین‌تر از",
        ])
        errors: list[str] = []
        error_details = []

        group_id = ""
        group_name = ""
        report_id = ""
        report_name = ""
        sql = None
        valid = False
        result = None
        answer = None
        explanation = None
        confidence = None
        generation_source = None
        validation = None
        intent = extract_intent(request.question, active_catalog)
        semantic_step_start = time.time()
        semantic_resolution = await semantic_resolver.resolve(request.question, semantic_snapshot)
        intent = semantic_resolver.enrich_intent(intent, semantic_resolution)
        suppress_name_substring_columns(intent, active_catalog)

        grounding_step_start = time.time()
        grounding = self._ground_question_values(
            request.question,
            tenant_id,
            intent,
            active_catalog,
        )
        tracer.add_step(
            "value_grounding",
            "success" if grounding.found_any or not grounding.ambiguous_tables else "warning",
            (time.time() - grounding_step_start) * 1000,
            data=grounding.audit_payload(),
        )
        value_override_applied = False
        if (
            grounding.recommended_table
            and intent.requested_entity in self.KNOWN_ENTITY_ROUTING
            and ENTITY_PRIMARY_TABLES.get(intent.requested_entity) != grounding.recommended_table
            and self._grounding_overrides_entity(grounding, intent, active_catalog, request.question)
        ):
            # The entity keyword is itself part of a grounded value phrase
            # (e.g. «کارمند اداری» naming requester_role); trust the value.
            intent.requested_entity = None
            value_override_applied = True

        normalized_intent = normalize_intent(intent)
        grounded_filter_dicts = [
            {"column": item.column, "operator": item.operator, "value": item.value}
            for item in grounding.grounded_filters
        ] if not intent.requested_entity else None
        # Legacy heuristics keep precedence for known generic-table questions;
        # value grounding acts as the fallback for everything else.
        semantic_table_plan = self._semantic_table_plan(
            request.question,
            active_catalog,
            grounded_filters=grounded_filter_dicts,
        )
        if semantic_table_plan is None and not intent.requested_entity and grounding.recommended_table:
            semantic_table_plan = self._semantic_table_plan(
                request.question,
                active_catalog,
                preferred_table=grounding.recommended_table,
                grounded_filters=grounded_filter_dicts,
            )
        # Generic runtime routing is reserved for newly discovered tables.
        # Known business entities have richer deterministic planners that must
        # preserve person names, national IDs, location joins, and profiles.
        if intent.requested_entity in {
            "student", "employee", "school", "salary", "retirement",
            "ranking", "organization",
        }:
            semantic_table_plan = None
        semantic_table_name = semantic_table_plan.required_tables[0] if semantic_table_plan and semantic_table_plan.required_tables else ""
        if semantic_table_plan and self._last_related_ambiguity:
            item = (self._last_related_ambiguity.get("items") or [{}])[0]
            if self._last_related_ambiguity.get("type") == "requested_column":
                label = item.get("label", "")
                columns = "، ".join(item.get("columns") or [])
                clarification_question = f"ستون «{label}» مبهم است و به چند ستون می‌تواند اشاره کند: {columns}. لطفاً دقیق‌تر مشخص کنید."
            else:
                tables = "، ".join(item.get("tables") or [])
                column = item.get("column", "")
                clarification_question = f"فیلتر «{column}» در چند جدول مرتبط پیدا شد: {tables}. لطفاً مشخص کنید منظورتان کدام مورد است."
            total_time = (time.time() - start_time) * 1000
            return PipelineResponse(
                question=request.question,
                success=False,
                rejected=False,
                unsupported=False,
                needs_clarification=True,
                clarification_question=clarification_question,
                group="training_request" if semantic_table_name == "demo_training_requests" else semantic_table_name,
                group_name="training_request" if semantic_table_name == "demo_training_requests" else semantic_table_name,
                sql=None,
                valid=False,
                result=None,
                answer=None,
                errors=[],
                intent=intent.model_dump(),
                trace=tracer.get_trace(),
                execution_time_ms=round(total_time, 2),
            )
        if semantic_table_name:
            semantic_table = active_catalog.table(semantic_table_name)
            ambiguity = self._ambiguous_value_filter_for_table(request.question, semantic_table) if semantic_table else None
            if ambiguity:
                total_time = (time.time() - start_time) * 1000
                columns = "، ".join(ambiguity["columns"])
                return PipelineResponse(
                    question=request.question,
                    success=False,
                    rejected=False,
                    unsupported=False,
                    needs_clarification=True,
                    clarification_question=f"مقدار «{ambiguity['value']}» در چند ستون پیدا شد: {columns}. لطفاً مشخص کنید منظورتان کدام ستون است.",
                    group="training_request" if semantic_table_name == "demo_training_requests" else semantic_table_name,
                    group_name="training_request" if semantic_table_name == "demo_training_requests" else semantic_table_name,
                    sql=None,
                    valid=False,
                    result=None,
                    answer=None,
                    errors=[],
                    intent=intent.model_dump(),
                    trace=tracer.get_trace(),
                    execution_time_ms=round(total_time, 2),
                )

        if intent.named_school:
            school_resolution = resolve_school_name(intent.named_school)
            if school_resolution.resolved_name:
                intent.named_school = school_resolution.resolved_name
            elif school_resolution.unavailable:
                pass
            elif "مدرسه" in request.question:
                total_time = (time.time() - start_time) * 1000
                return PipelineResponse(
                    question=request.question,
                    success=False,
                    rejected=False,
                    unsupported=False,
                    needs_clarification=True,
                    clarification_question=f"مدرسه «{intent.named_school}» در داده‌ها پیدا نشد. لطفاً نام مدرسه را دقیق‌تر وارد کنید.",
                    sql=None,
                    valid=False,
                    result=None,
                    answer=None,
                    errors=[],
                    intent=intent.model_dump(),
                    trace=tracer.get_trace(),
                    execution_time_ms=round(total_time, 2),
                )
            elif intent.province or intent.city or intent.province_values or intent.city_values or intent.grouping or intent.first_name or intent.last_name:
                intent.named_school = None
            elif school_resolution.ambiguous:
                candidates = "، ".join((school_resolution.candidates or [])[:5])
                total_time = (time.time() - start_time) * 1000
                return PipelineResponse(
                    question=request.question,
                    success=False,
                    rejected=False,
                    unsupported=False,
                    needs_clarification=True,
                    clarification_question=f"چند مدرسه با این نام پیدا شد. لطفاً دقیق‌تر مشخص کنید: {candidates}",
                    sql=None,
                    valid=False,
                    result=None,
                    answer=None,
                    errors=[],
                    intent=intent.model_dump(),
                    trace=tracer.get_trace(),
                    execution_time_ms=round(total_time, 2),
                )

        step_start = time.time()
        safety = safety_detector.detect(request.question)
        tracer.add_step("safety_intent_check", "success" if safety["is_safe"] else "rejected", (time.time() - step_start) * 1000, data=safety)
        if not safety["is_safe"]:
            total_time = (time.time() - start_time) * 1000
            return PipelineResponse(
                question=request.question,
                success=False,
                rejected=True,
                rejection_reason=safety["rejection_reason"],
                sql=None,
                result=None,
                answer=None,
                errors=[],
                trace=tracer.get_trace(),
                execution_time_ms=round(total_time, 2),
            )

        step_start = time.time()
        multi_intent = multi_intent_detector.detect(request.question)
        detected_multi_entities = set(multi_intent.get("detected_entities") or [])
        if (
            multi_intent.get("multi_intent")
            and not multi_intent.get("is_composable")
            and {"school", "student"}.issubset(detected_multi_entities)
            and (intent.province or intent.city)
        ):
            multi_intent["is_composable"] = True
            multi_intent["needs_clarification"] = False
            multi_intent["shared_grouping_dimension"] = "city" if intent.city else "province"
            multi_intent["decomposition_reason"] = None
        tracer.add_step("multi_intent_detection", "success", (time.time() - step_start) * 1000, data=multi_intent)
        if (
            multi_intent["multi_intent"]
            and not multi_intent.get("is_composable")
            and not intent.province_values
            and not intent.city_values
            and not (intent.requested_entity in {"student", "employee"} and (intent.first_name or intent.last_name))
        ):
            total_time = (time.time() - start_time) * 1000
            return PipelineResponse(
                question=request.question,
                success=False,
                rejected=False,
                unsupported=False,
                needs_clarification=True,
                clarification_question=multi_intent["clarification_question"],
                sql=None,
                valid=False,
                result=None,
                answer=None,
                errors=[],
                intent=intent.model_dump(),
                trace=tracer.get_trace(),
                execution_time_ms=round(total_time, 2),
            )

        step_start = time.time()
        ambiguity = detect_ambiguity(request.question)
        tracer.add_step("ambiguity_detection", "success", (time.time() - step_start) * 1000, data=ambiguity.model_dump())
        if ambiguity.needs_clarification:
            total_time = (time.time() - start_time) * 1000
            return PipelineResponse(
                question=request.question,
                success=False,
                rejected=False,
                unsupported=False,
                needs_clarification=True,
                clarification_question=ambiguity.clarification_question,
                sql=None,
                valid=False,
                result=None,
                answer=None,
                errors=[],
                intent=intent.model_dump(),
                trace=tracer.get_trace(),
                execution_time_ms=round(total_time, 2),
            )

        step_start = time.time()
        try:
            group_result = group_retriever.search_groups(tenant_id, request.question)
            group_id = group_result.get("group_id", "")
            group_name = group_result.get("group_name", "")
            if intent.requested_entity == "salary":
                group_id = "salary"
                group_name = "salary"
            if intent.requested_entity == "employee":
                group_id = "employee"
                group_name = "employee"
            if intent.requested_entity == "school":
                group_id = "student"
                group_name = "student"
            if intent.requested_entity == "retirement":
                group_id = "employee"
                group_name = "employee"
            if intent.requested_entity == "organization":
                # Canonical group label; retrieval may return legacy
                # «organization_unit» ids from older group artifacts.
                group_id = "organization"
                group_name = "organization"
            if semantic_table_plan:
                group_id = "training_request" if semantic_table_name == "demo_training_requests" else semantic_table_name
                group_name = group_id
            tracer.add_step("group_retrieval", "success", (time.time() - step_start) * 1000, data=group_result)
        except Exception as exc:
            errors.append(str(exc))
            error_details.append(pipeline_error_taxonomy.detail("retrieval.group_error", "group_retrieval", str(exc), severity="warning"))
            group_id, group_name = self._fallback_group(intent, semantic_table_name)
            tracer.add_step("group_retrieval", "error", (time.time() - step_start) * 1000, error=str(exc))

        step_start = time.time()
        try:
            report_result = report_retriever.search_reports(tenant_id, request.question, group_filter=group_id)
            report_id = self._select_report_id(intent, report_result.get("report_id", ""))
            if multi_intent.get("is_composable"):
                group_id = "student"
                group_name = "student"
                report_id = "school_statistics"
            report_obj = self._get_report(tenant_id, report_id) if report_id else None
            if multi_intent.get("is_composable"):
                report_obj = None
            report_name = report_obj.name if report_obj else report_result.get("report_name", "")
            if multi_intent.get("is_composable"):
                report_name = "Composable cross-domain statistics"
            if semantic_table_plan:
                report_id = f"semantic_table_{semantic_table_name}"
                report_name = "درخواست‌های آموزشی" if semantic_table_name == "demo_training_requests" else semantic_table_name
                report_obj = None
            tracer.add_step(
                "report_retrieval",
                "success",
                (time.time() - step_start) * 1000,
                data={
                    **report_result,
                    "selected_report_id": report_id,
                    "selected_report_name": report_name,
                },
            )
        except Exception as exc:
            errors.append(str(exc))
            error_details.append(pipeline_error_taxonomy.detail("retrieval.report_error", "report_retrieval", str(exc), severity="warning"))
            report_id, report_name, report_obj = self._fallback_report(intent, tenant_id, semantic_table_name)
            tracer.add_step("report_retrieval", "error", (time.time() - step_start) * 1000, error=str(exc))

        intent_payload = intent.model_dump()
        intent_payload["normalized"] = normalized_intent.model_dump()
        tracer.add_step("intent_extraction", "success", 0.0, data=intent_payload)
        tracer.add_step(
            "semantic_resolution",
            "success",
            (time.time() - semantic_step_start) * 1000,
            data={
                **semantic_resolution.model_dump(),
                "semantic_version": semantic_snapshot.version,
            },
        )
        tracer.add_step("intent_normalization", "success", 0.0, data=normalized_intent.model_dump())

        step_start = time.time()
        schema = schema_sync_service.load_schema(tenant_id)
        report_tables = [r.linked_table for r in self._get_all_reports(tenant_id)]
        unsupported_check = unsupported_detector.detect(request.question, schema, report_tables)
        tracer.add_step("unsupported_detection", "success" if unsupported_check["is_supported"] else "unsupported", (time.time() - step_start) * 1000, data=unsupported_check)
        if not unsupported_check["is_supported"]:
            total_time = (time.time() - start_time) * 1000
            return PipelineResponse(
                question=request.question,
                success=False,
                rejected=False,
                unsupported=True,
                unsupported_reason=unsupported_check["reason"],
                sql=None,
                result=None,
                answer=None,
                errors=[],
                intent=intent.model_dump(),
                trace=tracer.get_trace(),
                execution_time_ms=round(total_time, 2),
            )

        step_start = time.time()
        try:
            if semantic_table_plan:
                scoped_schema = schema
                plan = semantic_table_plan
            elif multi_intent.get("is_composable"):
                scoped_schema = schema
                dimension = multi_intent.get("shared_grouping_dimension") or "province"
                entities = set(multi_intent.get("detected_entities") or [])
                selected_columns = [f"COMPOSABLE_COUNTS_BY_{dimension.upper()}"]
                if {"school", "student"}.issubset(entities):
                    selected_columns.append("COMPOSABLE_SCHOOL_STUDENT")
                elif {"employee", "student"}.issubset(entities):
                    selected_columns.append("COMPOSABLE_EMPLOYEE_STUDENT")
                filters = []
                if dimension == "province" and intent.province:
                    filters.append({"column": "province", "operator": "=", "value": intent.province})
                if dimension == "city" and intent.city:
                    filters.append({"column": "city", "operator": "=", "value": intent.city})
                plan = SQLPlan(
                    required_tables=["organization_units", "employees", "schools", "students"],
                    selected_columns=selected_columns,
                    filters=filters,
                    aggregations=[{"function": "COUNT", "column": "*"}],
                    group_by=[dimension] if hasattr(SQLPlan, "group_by") else [],
                )
            elif (not complex_question) and (deterministic_plan := deterministic_sql_builder.build(normalized_intent, active_catalog)):
                scoped_schema = schema
                plan = deterministic_plan
            elif (
                (intent.requested_entity == "employee" and intent.aggregation == "COUNT" and intent.province)
                or (intent.requested_entity == "employee" and intent.city)
                or (intent.requested_entity == "employee" and intent.status)
                or (intent.requested_entity == "employee" and intent.grouping)
                or (intent.requested_entity == "employee" and (intent.first_name or intent.last_name))
                or (intent.requested_entity == "employee" and intent.national_id)
                or (intent.requested_entity == "employee" and (intent.position or intent.hire_year))
                or (intent.requested_entity == "salary" and (
                    intent.national_id or intent.first_name or intent.last_name or intent.status
                    or intent.position or intent.hire_year or intent.province or intent.city
                ))
                or (intent.requested_entity == "student" and intent.national_id)
                or (intent.requested_entity == "student" and intent.named_school)
                or (intent.requested_entity == "student" and intent.province)
                or (intent.requested_entity == "student" and intent.city)
                or (intent.requested_entity == "student" and intent.status)
                or (intent.requested_entity == "student" and intent.grouping)
                or (intent.requested_entity == "student" and (intent.first_name or intent.last_name))
                or (intent.requested_entity == "school" and intent.province)
                or (intent.requested_entity == "school" and intent.city)
                or (intent.requested_entity == "school" and intent.grouping)
                or (intent.requested_entity == "school" and intent.named_organization_unit)
                or (intent.requested_entity == "school" and (intent.school_type or intent.capacity_min or intent.established_year))
                or (intent.requested_entity == "organization" and intent.named_organization_unit)
                or (intent.requested_entity == "retirement" and intent.ranking_metric)
                or (intent.requested_entity == "school" and intent.wants_phone and intent.named_school)
                or (intent.requested_entity == "school" and intent.named_school)
            ):
                scoped_schema = schema
                plan = sql_planner.create_plan(request.question, scoped_schema, tenant_id=tenant_id, catalog=active_catalog)
                plan = self._apply_intent_to_plan(plan, intent, None, scoped_schema, semantic_catalog=active_catalog)
            else:
                scoped_schema = self._scope_schema(schema, report_obj)
                plan = sql_planner.create_plan(request.question, scoped_schema, tenant_id=tenant_id, catalog=active_catalog)
                plan = self._apply_intent_to_plan(plan, intent, report_obj, scoped_schema, semantic_catalog=active_catalog)
            tracer.add_step("sql_planning", "success", (time.time() - step_start) * 1000, data=plan.model_dump())
        except Exception as exc:
            errors.append(str(exc))
            error_details.append(pipeline_error_taxonomy.detail("sql.planning_error", "sql_planning", str(exc)))
            tracer.add_step("sql_planning", "error", (time.time() - step_start) * 1000, error=str(exc))
            plan = None
            scoped_schema = schema_sync_service.load_schema(tenant_id)

        if plan and (
            plan.planning_source == "deterministic_normalized_intent"
            or any(str(column).startswith("GENERIC_") for column in plan.selected_columns)
        ):
            join_verification = sql_plan_join_verifier.verify(plan, active_catalog, normalized_intent)
            tracer.add_step(
                "join_path_verification",
                "success" if join_verification.is_valid else "error",
                0.0,
                data=join_verification.model_dump(),
            )
            if not join_verification.is_valid:
                errors.extend(join_verification.errors)
                for join_error in join_verification.errors:
                    error_details.append(
                        pipeline_error_taxonomy.detail("sql.join_path_invalid", "join_path_verification", join_error)
                    )
                plan = None

        if plan:
            aggregate_safety = sql_aggregate_safety_guard.verify(plan, normalized_intent)
            aggregate_guard_is_hard = (
                plan.planning_source == "deterministic_normalized_intent"
                or any(str(column).startswith("GENERIC_") for column in plan.selected_columns)
            )
            tracer.add_step(
                "aggregate_safety",
                "success" if aggregate_safety.is_valid else ("error" if aggregate_guard_is_hard else "warning"),
                0.0,
                data=aggregate_safety.model_dump(),
            )
            if aggregate_guard_is_hard and not aggregate_safety.is_valid:
                errors.extend(aggregate_safety.errors)
                for aggregate_error in aggregate_safety.errors:
                    error_details.append(
                        pipeline_error_taxonomy.detail(
                            "sql.aggregate_safety_failed",
                            "aggregate_safety",
                            aggregate_error,
                        )
                    )
                plan = None

        if plan:
            # Confidence gate (roadmap Change 5): assess BEFORE generating.
            step_start = time.time()
            used_semantic_table_plan = semantic_table_plan is not None
            try:
                from backend.sql.templates import render_template_sql

                template_renderable = bool(render_template_sql(plan, active_catalog))
            except Exception:
                template_renderable = False
            assessment = confidence_policy.assess(
                intent_confidence=normalized_intent.confidence,
                requested_entity=intent.requested_entity,
                has_plan=True,
                plan_source=plan.planning_source,
                grounding=grounding,
                entity_binding_present=self._intent_has_binding_scalars(intent),
                used_value_override=value_override_applied,
                plan_template_approved=(
                    template_renderable
                    or any(
                        str(column).startswith(("TRAINING_REQUEST_", "GENERIC_TABLE_", "COMPOSABLE_"))
                        or "_GROUPED_BY_" in str(column)
                        for column in plan.selected_columns
                    )
                ),
            )
            tracer.add_step(
                "confidence_gate",
                "success" if not assessment.should_clarify else "warning",
                (time.time() - step_start) * 1000,
                data=assessment.model_dump(exclude_none=True),
            )
            if assessment.should_clarify:
                session_id = request.session_id or f"clarify-{uuid4().hex[:12]}"
                clarification_store.save(
                    ClarificationContext(
                        session_id=session_id,
                        original_question=request.question,
                        candidates=assessment.candidates,
                        missing_decision=assessment.reason,
                    )
                )
                total_time = (time.time() - start_time) * 1000
                return PipelineResponse(
                    question=request.question,
                    success=False,
                    rejected=False,
                    unsupported=False,
                    needs_clarification=True,
                    clarification_question=assessment.clarification_question,
                    group=group_id,
                    group_name=group_name,
                    sql=None,
                    valid=False,
                    result=None,
                    answer=None,
                    errors=[],
                    error_details=[
                        pipeline_error_taxonomy.detail(
                            "confidence.clarification_required",
                            "confidence_gate",
                            assessment.reason,
                            severity="warning",
                            user_message=assessment.clarification_question,
                        )
                    ],
                    intent=intent.model_dump(),
                    trace=tracer.get_trace(),
                    execution_time_ms=round(total_time, 2),
                    session_id=session_id,
                )

            step_start = time.time()
            safe_complex_template = (
                intent.requested_entity == "salary"
                and intent.aggregation in {"AVG", "SUM", "COUNT"}
                and bool(intent.grouping)
                and "مقایسه شهرها" not in question_text
                and "مقایسه استان ها" not in question_text
            ) or (
                intent.requested_entity == "school"
                and intent.aggregation == "COUNT"
                and bool(intent.grouping)
            ) or (
                # Approved deterministic templates for known generic tables stay
                # authoritative even for complex phrasings (e.g. numeric filters).
                plan is not None
                and any(
                    str(column).startswith("TRAINING_REQUEST_")
                    for column in plan.selected_columns
                )
            )
            generated = await sql_generator.generate(
                plan,
                scoped_schema,
                business_rules=request.question,
                report=report_obj,
                tenant_id=tenant_id,
                allow_template=(not complex_question) or safe_complex_template,
                semantic_snapshot=semantic_snapshot,
            )
            sql = generated.sql or None
            explanation = generated.explanation
            confidence = generated.confidence
            generation_source = generated.generation_source
            status = "success" if sql else "error"
            if not sql:
                errors.append(generated.explanation)
                error_code = (
                    "sql.llm_disabled"
                    if generated.generation_source == "llm_disabled"
                    else "sql.generation_failed"
                )
                error_details.append(pipeline_error_taxonomy.detail(error_code, "sql_generation", generated.explanation))
            tracer.add_step(
                "sql_generation",
                status,
                (time.time() - step_start) * 1000,
                data={
                    "sql_generated": bool(sql),
                    "explanation": explanation,
                    "generation_source": generation_source,
                    "llm_enabled": self.settings.llm_enabled,
                },
            )

        if sql:
            step_start = time.time()
            canonical_sql, canonicalization = canonicalize_sql_identifiers(sql, scoped_schema)
            if canonicalization["changed"]:
                sql = canonical_sql
                tracer.add_step(
                    "sql_identifier_canonicalization",
                    "success",
                    (time.time() - step_start) * 1000,
                    data=canonicalization,
                )

        if sql:
            step_start = time.time()
            validation_report = None if (
                semantic_table_plan
                or
                multi_intent.get("is_composable")
                or (intent.requested_entity == "employee" and intent.aggregation == "COUNT" and intent.province)
                or (intent.requested_entity == "employee" and intent.city)
                or (intent.requested_entity == "employee" and intent.status)
                or (intent.requested_entity == "employee" and intent.grouping)
                or (intent.requested_entity == "employee" and (intent.first_name or intent.last_name))
                or (intent.requested_entity == "employee" and intent.national_id)
                or (intent.requested_entity == "employee" and (intent.position or intent.hire_year))
                or (intent.requested_entity == "salary" and (
                    intent.national_id or intent.first_name or intent.last_name or intent.status
                    or intent.position or intent.hire_year or intent.province or intent.city
                ))
                or (intent.requested_entity == "student" and intent.national_id)
                or (intent.requested_entity == "student" and intent.named_school)
                or (intent.requested_entity == "student" and intent.province)
                or (intent.requested_entity == "student" and intent.city)
                or (intent.requested_entity == "student" and intent.status)
                or (intent.requested_entity == "student" and intent.grouping)
                or (intent.requested_entity == "student" and (intent.first_name or intent.last_name))
                or (intent.requested_entity == "school" and intent.province)
                or (intent.requested_entity == "school" and intent.city)
                or (intent.requested_entity == "school" and intent.grouping)
                or (intent.requested_entity == "school" and intent.named_organization_unit)
                or (intent.requested_entity == "school" and (intent.school_type or intent.capacity_min or intent.established_year))
                or (intent.requested_entity == "organization" and intent.named_organization_unit)
                or (intent.requested_entity == "retirement" and intent.ranking_metric)
                or (intent.requested_entity == "school" and intent.wants_phone and intent.named_school)
                or (intent.requested_entity == "school" and intent.named_school)
            ) else report_obj
            validation_intent = None if (semantic_table_plan or multi_intent.get("is_composable")) else intent
            required_contract = None
            if sql:
                # Build from the CURRENT intent so late mutations (e.g. fuzzy
                # school-name resolution) are reflected in the contract.
                required_contract = build_filter_contract(normalize_intent(intent), plan)
            validation = sql_validator.validate(
                sql,
                scoped_schema,
                report=validation_report,
                intent=validation_intent,
                contract=required_contract,
            )
            if not validation.is_valid:
                from backend.sql.repair_loop import sql_repair_loop

                repair = sql_repair_loop.repair(
                    sql,
                    scoped_schema,
                    report=validation_report,
                    intent=validation_intent,
                    contract=required_contract,
                )
                sql = repair.sql
                validation = repair.validation
                tracer.add_step(
                    "sql_repair",
                    "success" if repair.valid else "error",
                    0.0,
                    data=repair.model_dump(),
                )
            valid = validation.is_valid
            errors.extend(validation.errors)
            for validation_error in validation.errors:
                error_details.append(pipeline_error_taxonomy.detail("sql.validation_failed", "sql_validation", validation_error))
            tracer.add_step("sql_validation", "success" if valid else "error", (time.time() - step_start) * 1000, data=validation.model_dump())

        # Pre-execution result-contract gate (roadmap Change 4): the PLAN must
        # promise the contracted shape before any SQL runs.
        result_contract_obj = build_result_contract(normalized_intent, plan)
        if result_contract_obj is not None and sql:
            contract_step_start = time.time()
            contract_violations = validate_plan_shape(plan, result_contract_obj)
            tracer.add_step(
                "result_contract",
                "success" if not contract_violations else "error",
                (time.time() - contract_step_start) * 1000,
                data={"shape": result_contract_obj.shape, "violations": contract_violations},
            )
            if contract_violations:
                valid = False
                errors.extend(contract_violations)
                for violation in contract_violations:
                    error_details.append(
                        pipeline_error_taxonomy.detail(
                            "result.contract_failed", "result_contract", violation
                        )
                    )

        if valid and request.execute and sql:
            step_start = time.time()
            exec_result = execution_service.execute(QueryRequest(sql=sql))
            if exec_result.success:
                result = {
                    "columns": exec_result.columns,
                    "rows": exec_result.rows,
                    "row_count": exec_result.row_count,
                }
                result = data_sensitivity_policy.apply_to_result(result, sql=sql, tenant_id=request.tenant_id)
                tracer.add_step("sql_execution", "success", (time.time() - step_start) * 1000, data={"row_count": exec_result.row_count})
                result_shape = sql_result_shape_validator.verify(
                    result, normalized_intent, plan, contract=result_contract_obj
                )
                result_shape_is_hard = bool(
                    plan
                    and (
                        plan.planning_source == "deterministic_normalized_intent"
                        or any(str(column).startswith("GENERIC_") for column in plan.selected_columns)
                    )
                )
                tracer.add_step(
                    "result_shape_validation",
                    "success" if result_shape.is_valid else ("error" if result_shape_is_hard else "warning"),
                    0.0,
                    data=result_shape.model_dump(),
                )
                if result_shape_is_hard and not result_shape.is_valid:
                    valid = False
                    errors.extend(result_shape.errors)
                    for shape_error in result_shape.errors:
                        error_details.append(
                            pipeline_error_taxonomy.detail(
                                "result.shape_mismatch",
                                "result_shape_validation",
                                shape_error,
                            )
                        )
            else:
                errors.append(exec_result.error or "SQL execution failed")
                error_details.append(pipeline_error_taxonomy.detail("execution.failed", "sql_execution", exec_result.error or "SQL execution failed"))
                tracer.add_step("sql_execution", "error", (time.time() - step_start) * 1000, error=exec_result.error)

        if result is not None and valid:
            step_start = time.time()
            answer_result = await answer_service.generate_answer(
                question=request.question,
                result=result,
                report_name=report_name,
                group_name=group_name,
            )
            answer = answer_result.answer
            tracer.add_step("answer_generation", "success", (time.time() - step_start) * 1000, data={"answer_length": len(answer)})

        if sql:
            explanation = explainability_service.build(
                question=request.question,
                plan=plan,
                sql=sql,
                validation=validation,
                intent=intent,
                result=result,
                generator_explanation=explanation,
            )

        trace = tracer.get_trace()
        citations = citation_service.build(
            database=self.settings.database_name,
            tenant_id=tenant_id,
            sql=sql,
            group_id=group_id,
            report_id=report_id,
            generation_source=generation_source,
            trace=trace,
        )

        total_time = (time.time() - start_time) * 1000
        return PipelineResponse(
            question=request.question,
            success=valid and (result is not None or not request.execute),
            rejected=False,
            unsupported=False,
            needs_clarification=False,
            group=group_id,
            group_name=group_name,
            report=report_id,
            report_name=report_name,
            sql=sql,
            valid=valid,
            result=result,
            answer=answer,
            errors=errors,
            error_details=error_details,
            intent=intent_payload,
            explanation=explanation,
            confidence=confidence,
            generation_source=generation_source,
            citations=citations,
            trace=trace,
            execution_time_ms=round(total_time, 2),
            session_id=request.session_id,
        )

    def _get_all_reports(self, tenant_id: str) -> List[Report]:
        tenant_path = self.tenants_dir / tenant_id
        loader = KnowledgeLoader(tenant_path)
        return loader.load_all_reports()


query_pipeline = QueryPipeline()
