import json
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional

from backend.config import get_settings
from backend.database.models import SchemaDiscoverySnapshot
from backend.semantic.loader import clear_semantic_catalog_cache
from backend.semantic.context_index import semantic_context_index_service
from backend.semantic.models import (
    SemanticActivationResponse,
    SemanticCatalog,
    SemanticColumn,
    SemanticJoin,
    SemanticMetric,
    SemanticRule,
    SemanticRollbackResponse,
    SemanticSuggestionSet,
    SemanticTable,
    SemanticValidationIssue,
    SemanticVersionInfo,
)


class SemanticActivationService:
    def __init__(self):
        self.settings = get_settings()
        self.schema_root = Path(__file__).parent.parent.parent / "schema" / "tenants"

    def _tenant_dir(self, tenant_id: str) -> Path:
        tenant_dir = self.schema_root / tenant_id
        tenant_dir.mkdir(parents=True, exist_ok=True)
        return tenant_dir

    def discovery_path(self, tenant_id: str) -> Path:
        return self._tenant_dir(tenant_id) / "discovery.json"

    def suggestions_path(self, tenant_id: str) -> Path:
        return self._tenant_dir(tenant_id) / "semantic_suggestions.json"

    def active_catalog_path(self, tenant_id: str) -> Path:
        return self._tenant_dir(tenant_id) / "semantic_active.json"

    def versions_dir(self, tenant_id: str) -> Path:
        path = self._tenant_dir(tenant_id) / "semantic_versions"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _version_metadata_path(self, version_path: Path) -> Path:
        return version_path.with_suffix(".meta.json")

    def _catalog_counts(self, catalog: SemanticCatalog) -> dict[str, int]:
        return {
            "tables": len(catalog.tables),
            "joins": len(catalog.joins),
            "rules": len(catalog.rules),
        }

    def load_discovery(self, tenant_id: str) -> SchemaDiscoverySnapshot:
        with self.discovery_path(tenant_id).open("r", encoding="utf-8") as file:
            return SchemaDiscoverySnapshot.model_validate(json.load(file))

    def load_suggestions(self, tenant_id: str) -> SemanticSuggestionSet:
        with self.suggestions_path(tenant_id).open("r", encoding="utf-8") as file:
            return SemanticSuggestionSet.model_validate(json.load(file))

    def load_active_catalog(self, tenant_id: Optional[str] = None) -> SemanticCatalog:
        tenant = tenant_id or self.settings.tenant_id
        with self.active_catalog_path(tenant).open("r", encoding="utf-8") as file:
            return SemanticCatalog.model_validate(json.load(file))

    def backup_active_catalog(
        self,
        tenant_id: str,
        reason: str = "before_activation",
        source_fingerprint: str = "",
    ) -> Optional[Path]:
        active_path = self.active_catalog_path(tenant_id)
        if not active_path.exists():
            return None

        catalog = self.load_active_catalog(tenant_id)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        version_id = f"{timestamp}_{reason}"
        version_path = self.versions_dir(tenant_id) / f"{version_id}.json"
        shutil.copy2(active_path, version_path)
        metadata = SemanticVersionInfo(
            version_id=version_id,
            path=str(version_path),
            created_at=datetime.now().isoformat(timespec="seconds"),
            source_fingerprint=source_fingerprint,
            reason=reason,
            **self._catalog_counts(catalog),
        )
        with self._version_metadata_path(version_path).open("w", encoding="utf-8") as file:
            json.dump(metadata.model_dump(), file, ensure_ascii=False, indent=2)
        return version_path

    def list_versions(self, tenant_id: Optional[str] = None) -> list[SemanticVersionInfo]:
        tenant = tenant_id or self.settings.tenant_id
        versions = []
        for path in sorted(self.versions_dir(tenant).glob("*.json"), reverse=True):
            if path.name.endswith(".meta.json"):
                continue
            metadata_path = self._version_metadata_path(path)
            if metadata_path.exists():
                with metadata_path.open("r", encoding="utf-8") as file:
                    versions.append(SemanticVersionInfo.model_validate(json.load(file)))
            else:
                version_id = path.stem
                versions.append(
                    SemanticVersionInfo(
                        version_id=version_id,
                        path=str(path),
                        created_at="",
                    )
                )
        return versions

    def validate(
        self,
        suggestions: SemanticSuggestionSet,
        discovery: SchemaDiscoverySnapshot,
    ) -> list[SemanticValidationIssue]:
        issues: list[SemanticValidationIssue] = []
        live_tables = {table.name: table for table in discovery.tables}
        live_columns = {
            table.name: {column.name for column in table.columns}
            for table in discovery.tables
        }

        if suggestions.source_fingerprint != discovery.fingerprint:
            issues.append(
                SemanticValidationIssue(
                    severity="error",
                    code="fingerprint_mismatch",
                    message="Semantic suggestions were generated from a different schema snapshot.",
                    path="source_fingerprint",
                )
            )

        for table in suggestions.tables:
            if table.name not in live_tables:
                issues.append(
                    SemanticValidationIssue(
                        severity="error",
                        code="unknown_table",
                        message=f"Table '{table.name}' does not exist in discovery snapshot.",
                        path=f"tables.{table.name}",
                    )
                )
                continue

            for column_name in [table.primary_key, *table.default_display_columns, *table.profile_columns]:
                if column_name and column_name not in live_columns[table.name]:
                    issues.append(
                        SemanticValidationIssue(
                            severity="error",
                            code="unknown_column_reference",
                            message=f"Column '{table.name}.{column_name}' does not exist.",
                            path=f"tables.{table.name}",
                        )
                    )

            for column in table.columns:
                if column.name not in live_columns[table.name]:
                    issues.append(
                        SemanticValidationIssue(
                            severity="error",
                            code="unknown_column",
                            message=f"Column '{table.name}.{column.name}' does not exist.",
                            path=f"tables.{table.name}.columns.{column.name}",
                        )
                    )

            if table.review_required:
                issues.append(
                    SemanticValidationIssue(
                        severity="warning",
                        code="review_required",
                        message=f"Table '{table.name}' has low-confidence semantic suggestions.",
                        path=f"tables.{table.name}",
                    )
                )

        for join in suggestions.joins:
            if join.from_table not in live_columns:
                issues.append(
                    SemanticValidationIssue(
                        severity="error",
                        code="unknown_join_table",
                        message=f"Join source table '{join.from_table}' does not exist.",
                        path=f"joins.{join.from_table}.{join.from_column}",
                    )
                )
                continue
            if join.to_table not in live_columns:
                issues.append(
                    SemanticValidationIssue(
                        severity="error",
                        code="unknown_join_table",
                        message=f"Join target table '{join.to_table}' does not exist.",
                        path=f"joins.{join.to_table}.{join.to_column}",
                    )
                )
                continue
            if join.from_column not in live_columns[join.from_table]:
                issues.append(
                    SemanticValidationIssue(
                        severity="error",
                        code="unknown_join_column",
                        message=f"Join source column '{join.from_table}.{join.from_column}' does not exist.",
                        path=f"joins.{join.from_table}.{join.from_column}",
                    )
                )
            if join.to_column not in live_columns[join.to_table]:
                issues.append(
                    SemanticValidationIssue(
                        severity="error",
                        code="unknown_join_column",
                        message=f"Join target column '{join.to_table}.{join.to_column}' does not exist.",
                        path=f"joins.{join.to_table}.{join.to_column}",
                    )
                )

        for term in suggestions.business_terms:
            if "." not in term.maps_to:
                issues.append(
                    SemanticValidationIssue(
                        severity="error",
                        code="invalid_business_term_target",
                        message=f"Business term '{term.term_fa}' must map to table.column.",
                        path=f"business_terms.{term.term_fa}",
                    )
                )
                continue
            table_name, column_name = term.maps_to.split(".", 1)
            if table_name not in live_columns or column_name not in live_columns[table_name]:
                issues.append(
                    SemanticValidationIssue(
                        severity="error",
                        code="unknown_business_term_target",
                        message=f"Business term '{term.term_fa}' maps to unknown column '{term.maps_to}'.",
                        path=f"business_terms.{term.term_fa}",
                    )
                )

        for metric in suggestions.metrics:
            if metric.table not in live_columns:
                issues.append(SemanticValidationIssue(
                    severity="error", code="unknown_metric_table",
                    message=f"Metric '{metric.name}' targets unknown table '{metric.table}'.",
                    path=f"metrics.{metric.name}",
                ))
            qualified_columns = re.findall(r"\b([a-z_][a-z0-9_]*)\.([a-z_][a-z0-9_]*)\b", metric.expression, re.I)
            for table_name, column_name in qualified_columns:
                if table_name not in live_columns or column_name not in live_columns[table_name]:
                    issues.append(SemanticValidationIssue(
                        severity="error", code="unknown_metric_column",
                        message=f"Metric '{metric.name}' references unknown column '{table_name}.{column_name}'.",
                        path=f"metrics.{metric.name}.expression",
                    ))
            if ";" in metric.expression or any(
                keyword in metric.expression.upper()
                for keyword in ["INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "CREATE"]
            ):
                issues.append(SemanticValidationIssue(
                    severity="error", code="unsafe_metric_expression",
                    message=f"Metric '{metric.name}' has an unsafe expression.",
                    path=f"metrics.{metric.name}.expression",
                ))

        for mapping in suggestions.value_mappings:
            if "." not in mapping.column:
                issues.append(
                    SemanticValidationIssue(
                        severity="error",
                        code="invalid_value_mapping_column",
                        message=f"Value mapping '{mapping.term_fa}' must target table.column.",
                        path=f"value_mappings.{mapping.term_fa}",
                    )
                )
                continue
            table_name, column_name = mapping.column.split(".", 1)
            if table_name not in live_columns or column_name not in live_columns[table_name]:
                issues.append(
                    SemanticValidationIssue(
                        severity="error",
                        code="unknown_value_mapping_column",
                        message=f"Value mapping '{mapping.term_fa}' targets unknown column '{mapping.column}'.",
                        path=f"value_mappings.{mapping.term_fa}",
                    )
                )

        return issues

    def build_active_catalog(self, suggestions: SemanticSuggestionSet) -> SemanticCatalog:
        tables = [
            SemanticTable(
                name=table.name,
                entity=table.entity,
                description=table.description_fa,
                aliases=table.aliases_fa,
                primary_key=table.primary_key,
                default_display_columns=table.default_display_columns,
                profile_columns=table.profile_columns,
                columns=[
                    SemanticColumn(
                        name=column.name,
                        data_type=column.data_type,
                        description=column.description_fa,
                        aliases=column.aliases_fa,
                        value_type=column.value_type,
                        pii=column.pii,
                    )
                    for column in table.columns
                ],
            )
            for table in suggestions.tables
        ]
        joins = [
            SemanticJoin(
                from_table=join.from_table,
                from_column=join.from_column,
                to_table=join.to_table,
                to_column=join.to_column,
                description=join.description_fa,
                cardinality=join.cardinality,
            )
            for join in suggestions.joins
        ]
        rules = [
            SemanticRule(
                name=rule.name,
                description=rule.description_fa,
                applies_to=rule.applies_to,
            )
            for rule in suggestions.rules
        ]
        for term in suggestions.business_terms:
            rules.append(
                SemanticRule(
                    name=f"business_term_{term.maps_to.replace('.', '_')}",
                    description=f"{term.term_fa}: {term.description_fa} maps_to={term.maps_to}; aliases={', '.join(term.aliases_fa)}",
                    applies_to=[term.maps_to],
                )
            )
        for mapping in suggestions.value_mappings:
            rules.append(
                SemanticRule(
                    name=f"value_mapping_{mapping.column.replace('.', '_')}_{mapping.value}",
                    description=f"{mapping.term_fa}: {mapping.description_fa} value={mapping.value}; aliases={', '.join(mapping.aliases_fa)}",
                    applies_to=[mapping.column],
                )
            )
        return SemanticCatalog(
            version=suggestions.version,
            language=suggestions.language,
            tables=tables,
            joins=joins,
            rules=rules,
            value_mappings=[mapping.model_dump() for mapping in suggestions.value_mappings],
            business_terms=[term.model_dump() for term in suggestions.business_terms],
            metrics=[
                SemanticMetric(
                    name=metric.name,
                    table=metric.table,
                    expression=metric.expression,
                    aggregation=metric.aggregation,
                    description=metric.description_fa,
                    aliases=metric.aliases_fa,
                )
                for metric in suggestions.metrics
            ],
        )

    def save_active_catalog(self, tenant_id: str, catalog: SemanticCatalog, source_fingerprint: str = "") -> tuple[Path, Optional[Path]]:
        backup_path = self.backup_active_catalog(
            tenant_id,
            reason="before_activation",
            source_fingerprint=source_fingerprint,
        )
        path = self.active_catalog_path(tenant_id)
        temporary_path = path.with_suffix(".tmp")
        with temporary_path.open("w", encoding="utf-8") as file:
            json.dump(catalog.model_dump(), file, ensure_ascii=False, indent=2)
        temporary_path.replace(path)
        clear_semantic_catalog_cache()
        semantic_context_index_service.clear()
        semantic_context_index_service.get_or_build(tenant_id, catalog)
        return path, backup_path

    def activate(self, tenant_id: Optional[str] = None, force: bool = False) -> SemanticActivationResponse:
        tenant = tenant_id or self.settings.tenant_id
        discovery = self.load_discovery(tenant)
        suggestions = self.load_suggestions(tenant)
        issues = self.validate(suggestions, discovery)
        has_errors = any(issue.severity == "error" for issue in issues)

        if has_errors and not force:
            return SemanticActivationResponse(
                status="blocked",
                tenant_id=tenant,
                source_fingerprint=suggestions.source_fingerprint,
                issues=issues,
            )

        catalog = self.build_active_catalog(suggestions)
        active_path, backup_path = self.save_active_catalog(
            tenant,
            catalog,
            source_fingerprint=suggestions.source_fingerprint,
        )
        return SemanticActivationResponse(
            status="activated_with_warnings" if issues else "activated",
            tenant_id=tenant,
            source_fingerprint=suggestions.source_fingerprint,
            active_catalog_path=str(active_path),
            backup_path=str(backup_path) if backup_path else None,
            issues=issues,
            tables=len(catalog.tables),
            joins=len(catalog.joins),
            rules=len(catalog.rules),
        )

    def validate_current(self, tenant_id: Optional[str] = None) -> SemanticActivationResponse:
        tenant = tenant_id or self.settings.tenant_id
        discovery = self.load_discovery(tenant)
        suggestions = self.load_suggestions(tenant)
        issues = self.validate(suggestions, discovery)
        return SemanticActivationResponse(
            status="valid" if not any(issue.severity == "error" for issue in issues) else "invalid",
            tenant_id=tenant,
            source_fingerprint=suggestions.source_fingerprint,
            issues=issues,
            tables=len(suggestions.tables),
            joins=len(suggestions.joins),
            rules=len(suggestions.rules),
        )

    def rollback(self, version_id: str, tenant_id: Optional[str] = None) -> SemanticRollbackResponse:
        tenant = tenant_id or self.settings.tenant_id
        version_path = self.versions_dir(tenant) / f"{version_id}.json"
        if not version_path.exists():
            return SemanticRollbackResponse(
                status="not_found",
                tenant_id=tenant,
                restored_version_id=version_id,
                message=f"Version '{version_id}' was not found.",
            )

        backup_path = self.backup_active_catalog(tenant, reason="before_rollback")
        active_path = self.active_catalog_path(tenant)
        shutil.copy2(version_path, active_path)
        clear_semantic_catalog_cache()
        semantic_context_index_service.clear()
        restored_catalog = self.load_active_catalog(tenant)
        semantic_context_index_service.get_or_build(tenant, restored_catalog)
        return SemanticRollbackResponse(
            status="rolled_back",
            tenant_id=tenant,
            restored_version_id=version_id,
            active_catalog_path=str(active_path),
            backup_path=str(backup_path) if backup_path else None,
            message=f"Restored semantic catalog version '{version_id}'.",
        )


semantic_activation_service = SemanticActivationService()
