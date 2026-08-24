import time
from pathlib import Path
from typing import Optional

from backend.config import get_settings
from backend.database.discovery_service import schema_discovery_service
from backend.database.onboarding_service import database_onboarding_service
from backend.database.sync_service import schema_sync_service
from backend.semantic.activation_service import semantic_activation_service
from backend.semantic.benchmark_service import semantic_benchmark_service
from backend.semantic.models import (
    SemanticAutoUpdateResponse,
    SemanticFreshnessResponse,
    SemanticLifecycleResponse,
    SemanticLifecycleStep,
)
from backend.semantic.suggestion_service import semantic_suggestion_service
from backend.value_index.service import value_index_service
from backend.sync.incremental_service import incremental_sync_service


class SemanticLifecycleService:
    def __init__(self):
        self.settings = get_settings()

    def check_freshness(
        self,
        tenant_id: Optional[str] = None,
        schema_name: str = "public",
        sample_size: int = 3,
        sample_value_limit: int = 8,
    ) -> SemanticFreshnessResponse:
        tenant = tenant_id or self.settings.tenant_id
        active_exists = semantic_activation_service.active_catalog_path(tenant).exists()
        discovery_exists = semantic_activation_service.discovery_path(tenant).exists()
        suggestions_exist = semantic_activation_service.suggestions_path(tenant).exists()

        try:
            current = schema_discovery_service.discover(
                tenant_id=tenant,
                schema_name=schema_name,
                sample_size=sample_size,
                sample_value_limit=sample_value_limit,
            )
        except Exception as exc:
            return SemanticFreshnessResponse(
                status="error",
                tenant_id=tenant,
                active_catalog_exists=active_exists,
                discovery_exists=discovery_exists,
                suggestions_exist=suggestions_exist,
                message=f"Could not inspect current database: {exc}",
                recommended_action="Check PostgreSQL connection and run semantic lifecycle after the database is available.",
            )

        stored_fingerprint = ""
        suggestions_fingerprint = ""
        if discovery_exists:
            stored_fingerprint = semantic_activation_service.load_discovery(tenant).fingerprint
        if suggestions_exist:
            suggestions_fingerprint = semantic_activation_service.load_suggestions(tenant).source_fingerprint

        if not active_exists or not discovery_exists or not suggestions_exist:
            return SemanticFreshnessResponse(
                status="missing_metadata",
                tenant_id=tenant,
                current_fingerprint=current.fingerprint,
                stored_fingerprint=stored_fingerprint,
                suggestions_fingerprint=suggestions_fingerprint,
                active_catalog_exists=active_exists,
                discovery_exists=discovery_exists,
                suggestions_exist=suggestions_exist,
                tables_discovered=len(current.tables),
                relationships_found=len(current.relationships),
                message="Semantic metadata is incomplete.",
                recommended_action="Run the full semantic lifecycle once to create discovery, suggestions, active catalog, and benchmark results.",
            )

        if current.fingerprint != stored_fingerprint or suggestions_fingerprint != stored_fingerprint:
            return SemanticFreshnessResponse(
                status="stale",
                tenant_id=tenant,
                current_fingerprint=current.fingerprint,
                stored_fingerprint=stored_fingerprint,
                suggestions_fingerprint=suggestions_fingerprint,
                active_catalog_exists=active_exists,
                discovery_exists=discovery_exists,
                suggestions_exist=suggestions_exist,
                tables_discovered=len(current.tables),
                relationships_found=len(current.relationships),
                message="Database structure or sampled values changed after the semantic layer was generated.",
                recommended_action="Run /semantic/lifecycle/run before relying on answers from the updated database.",
            )

        return SemanticFreshnessResponse(
            status="up_to_date",
            tenant_id=tenant,
            current_fingerprint=current.fingerprint,
            stored_fingerprint=stored_fingerprint,
            suggestions_fingerprint=suggestions_fingerprint,
            active_catalog_exists=active_exists,
            discovery_exists=discovery_exists,
            suggestions_exist=suggestions_exist,
            tables_discovered=len(current.tables),
            relationships_found=len(current.relationships),
            message="Semantic layer matches the current database fingerprint.",
            recommended_action="No action is required.",
        )

    async def ensure_updated(
        self,
        tenant_id: Optional[str] = None,
        schema_name: str = "public",
        sample_size: int = 3,
        sample_value_limit: int = 8,
        min_pass_rate: float = 95.0,
        benchmark_limit: Optional[int] = None,
        force_activate: bool = False,
    ) -> SemanticAutoUpdateResponse:
        tenant = tenant_id or self.settings.tenant_id
        freshness_before = self.check_freshness(
            tenant_id=tenant,
            schema_name=schema_name,
            sample_size=sample_size,
            sample_value_limit=sample_value_limit,
        )

        if freshness_before.status == "up_to_date":
            return SemanticAutoUpdateResponse(
                status="skipped",
                tenant_id=tenant,
                action="none",
                freshness_before=freshness_before,
                message="Semantic layer is already up to date; lifecycle was not run.",
            )

        if freshness_before.status == "error":
            return SemanticAutoUpdateResponse(
                status="failed",
                tenant_id=tenant,
                action="none",
                freshness_before=freshness_before,
                message="Could not check the database safely, so automatic update was not run.",
            )

        if (
            freshness_before.status == "stale"
            and freshness_before.active_catalog_exists
            and freshness_before.discovery_exists
            and freshness_before.suggestions_exist
        ):
            try:
                incremental = await incremental_sync_service.run(
                    tenant_id=tenant,
                    schema_name=schema_name,
                    sample_size=sample_size,
                    sample_value_limit=sample_value_limit,
                    min_pass_rate=min_pass_rate,
                    benchmark_limit=benchmark_limit,
                    force_activate=force_activate,
                )
                freshness_after = self.check_freshness(
                    tenant_id=tenant,
                    schema_name=schema_name,
                    sample_size=sample_size,
                    sample_value_limit=sample_value_limit,
                )
                success = (
                    incremental.get("status") in {"ready", "skipped"}
                    and freshness_after.status == "up_to_date"
                )
                return SemanticAutoUpdateResponse(
                    status="updated" if success else str(incremental.get("status", "failed")),
                    tenant_id=tenant,
                    action="incremental_sync",
                    freshness_before=freshness_before,
                    incremental_sync=incremental,
                    freshness_after=freshness_after,
                    message=(
                        "Changed tables were synchronized incrementally."
                        if success
                        else "Incremental synchronization ran but did not pass every quality gate."
                    ),
                )
            except Exception:
                # A full lifecycle is the safe recovery path for missing or incompatible checkpoints.
                pass

        lifecycle = await self.run(
            tenant_id=tenant,
            schema_name=schema_name,
            sample_size=sample_size,
            sample_value_limit=sample_value_limit,
            min_pass_rate=min_pass_rate,
            benchmark_limit=benchmark_limit,
            force_activate=force_activate,
        )
        freshness_after = self.check_freshness(
            tenant_id=tenant,
            schema_name=schema_name,
            sample_size=sample_size,
            sample_value_limit=sample_value_limit,
        )

        success = lifecycle.status == "ready" and freshness_after.status == "up_to_date"
        return SemanticAutoUpdateResponse(
            status="updated" if success else lifecycle.status,
            tenant_id=tenant,
            action="lifecycle_run",
            freshness_before=freshness_before,
            lifecycle=lifecycle,
            freshness_after=freshness_after,
            message=(
                "Semantic layer was rebuilt, activated, benchmarked, and now matches the database."
                if success
                else "Automatic update ran, but the semantic layer is not ready yet."
            ),
        )

    async def run(
        self,
        tenant_id: Optional[str] = None,
        schema_name: str = "public",
        sample_size: int = 3,
        sample_value_limit: int = 8,
        min_pass_rate: float = 95.0,
        benchmark_limit: Optional[int] = None,
        force_activate: bool = False,
    ) -> SemanticLifecycleResponse:
        tenant = tenant_id or self.settings.tenant_id
        steps: list[SemanticLifecycleStep] = []

        discovery_result = schema_discovery_service.sync_discovery(
            tenant_id=tenant,
            schema_name=schema_name,
            sample_size=sample_size,
            sample_value_limit=sample_value_limit,
        )
        steps.append(
            SemanticLifecycleStep(
                name="schema_discovery",
                status=discovery_result.status,
                message=f"Discovered {discovery_result.tables_discovered} tables and {discovery_result.relationships_found} relationships.",
                output_path=discovery_result.output_path,
                details={
                    "tables_discovered": discovery_result.tables_discovered,
                    "relationships_found": discovery_result.relationships_found,
                    "fingerprint": discovery_result.fingerprint,
                },
            )
        )
        if discovery_result.status != "success":
            return SemanticLifecycleResponse(
                status="failed",
                tenant_id=tenant,
                source_fingerprint=discovery_result.fingerprint,
                steps=steps,
                discovery=discovery_result,
            )

        schema_sync_result = schema_sync_service.sync_schema(tenant)
        steps.append(
            SemanticLifecycleStep(
                name="validator_schema_sync",
                status=schema_sync_result.status,
                message=(
                    f"Synced validator schema cache with {schema_sync_result.tables_discovered} tables "
                    f"and {schema_sync_result.relationships_found} relationships."
                ),
                details=schema_sync_result.model_dump(mode="json"),
            )
        )
        if schema_sync_result.status != "success":
            return SemanticLifecycleResponse(
                status="failed",
                tenant_id=tenant,
                source_fingerprint=discovery_result.fingerprint,
                steps=steps,
                discovery=discovery_result,
            )

        discovery_snapshot = database_onboarding_service.load_snapshot(tenant)
        quality_gate = database_onboarding_service.quality_gate(discovery_snapshot)
        steps.append(
            SemanticLifecycleStep(
                name="schema_quality_gate",
                status=quality_gate["status"],
                message=quality_gate["message"],
                details={
                    "summary": quality_gate["summary"],
                    "blockers": quality_gate["blockers"],
                    "warnings": quality_gate["warnings"],
                    "recommended_actions": quality_gate["recommended_actions"],
                },
            )
        )
        if quality_gate["status"] == "blocked":
            return SemanticLifecycleResponse(
                status="blocked",
                tenant_id=tenant,
                source_fingerprint=discovery_result.fingerprint,
                steps=steps,
                discovery=discovery_result,
            )

        suggestions, suggestions_path = semantic_suggestion_service.sync(tenant_id=tenant)
        review_required = sum(1 for table in suggestions.tables if table.review_required)
        steps.append(
            SemanticLifecycleStep(
                name="semantic_suggestions",
                status="success",
                message=f"Generated semantic draft for {len(suggestions.tables)} tables.",
                output_path=str(suggestions_path),
                details={
                    "tables": len(suggestions.tables),
                    "joins": len(suggestions.joins),
                    "business_terms": len(suggestions.business_terms),
                    "value_mappings": len(suggestions.value_mappings),
                    "rules": len(suggestions.rules),
                    "review_required_tables": review_required,
                },
            )
        )

        # LLM-assisted Persian alias enrichment (optional, cached).
        from backend.semantic.alias_enrichment import alias_enrichment_service

        enrichment_start = time.time()
        suggestions, enrich_stats = await alias_enrichment_service.enrich_suggestions(
            tenant, suggestions
        )
        steps.append(
            SemanticLifecycleStep(
                name="alias_enrichment",
                status="success" if enrich_stats.get("enabled") else "warning",
                message=(
                    f"Alias enrichment: {enrich_stats.get('aliases_added', 0)} Persian aliases "
                    f"added across {enrich_stats.get('columns_enriched', 0)} columns "
                    f"(prompted={enrich_stats.get('prompted', 0)}, "
                    f"cache_hits={enrich_stats.get('cache_hits', 0)})."
                    if enrich_stats.get("enabled")
                    else f"Alias enrichment skipped: {enrich_stats.get('reason')}"
                ),
                details=enrich_stats,
            )
        )

        column_aliases = {
            f"{table.name}.{column.name}": [
                column.name,
                column.display_name_fa,
                *column.aliases_fa,
            ]
            for table in suggestions.tables
            for column in table.columns
        }
        pii_columns = {
            f"{table.name}.{column.name}"
            for table in suggestions.tables
            for column in table.columns
            if column.pii
        }
        value_index, value_index_path = value_index_service.sync(
            discovery_snapshot,
            column_aliases=column_aliases,
            pii_columns=pii_columns,
        )
        deep_stats: dict = {}
        if self.settings.value_index_deep_enabled:
            try:
                value_index, deep_stats = value_index_service.deep_refresh(
                    value_index, discovery_snapshot
                )
                value_index_path = value_index_service.save(value_index)
            except Exception as exc:  # deep refresh must never break onboarding
                deep_stats = {"error": str(exc)}
        steps.append(
            SemanticLifecycleStep(
                name="value_index_sync",
                status="success",
                message=(
                    f"Indexed {len(value_index.entries)} safe categorical values; "
                    f"excluded {len(value_index.excluded_columns)} columns."
                ),
                output_path=str(value_index_path),
                details={
                    "entries": len(value_index.entries),
                    "excluded_columns": len(value_index.excluded_columns),
                    "source_fingerprint": value_index.source_fingerprint,
                },
            )
        )

        activation = semantic_activation_service.activate(tenant, force=force_activate)
        steps.append(
            SemanticLifecycleStep(
                name="semantic_activation",
                status=activation.status,
                message=f"Activation completed with {len(activation.issues)} issues.",
                output_path=activation.active_catalog_path,
                details={
                    "tables": activation.tables,
                    "joins": activation.joins,
                    "rules": activation.rules,
                    "issues": [issue.model_dump(mode="json") for issue in activation.issues],
                },
            )
        )
        if activation.status == "blocked":
            return SemanticLifecycleResponse(
                status="blocked",
                tenant_id=tenant,
                source_fingerprint=activation.source_fingerprint,
                steps=steps,
                discovery=discovery_result,
                activation=activation,
            )

        benchmark = await semantic_benchmark_service.run(
            tenant_id=tenant,
            min_pass_rate=min_pass_rate,
            limit=benchmark_limit,
        )
        steps.append(
            SemanticLifecycleStep(
                name="semantic_benchmark",
                status=benchmark.status,
                message=f"Benchmark {benchmark.summary.passed}/{benchmark.summary.total} passed ({benchmark.summary.pass_rate}%).",
                output_path=benchmark.output_path,
                details=benchmark.summary.model_dump(mode="json"),
            )
        )

        return SemanticLifecycleResponse(
            status="ready" if benchmark.status == "passed" else "failed",
            tenant_id=tenant,
            source_fingerprint=benchmark.source_fingerprint,
            steps=steps,
            discovery=discovery_result,
            activation=activation,
            benchmark=benchmark,
        )

    def run_sync(
        self,
        tenant_id: Optional[str] = None,
        schema_name: str = "public",
        sample_size: int = 3,
        sample_value_limit: int = 8,
        min_pass_rate: float = 95.0,
        benchmark_limit: Optional[int] = None,
        force_activate: bool = False,
    ) -> SemanticLifecycleResponse:
        import asyncio

        return asyncio.run(
            self.run(
                tenant_id=tenant_id,
                schema_name=schema_name,
                sample_size=sample_size,
                sample_value_limit=sample_value_limit,
                min_pass_rate=min_pass_rate,
                benchmark_limit=benchmark_limit,
                force_activate=force_activate,
            )
        )


semantic_lifecycle_service = SemanticLifecycleService()
