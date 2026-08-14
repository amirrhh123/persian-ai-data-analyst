from __future__ import annotations

from pydantic import BaseModel, Field

from backend.database.models import SchemaDiscoveryResponse


_DIGIT_TRANSLATION = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


def normalize_identifier(value: str) -> str:
    return (value or "").translate(_DIGIT_TRANSLATION).lower().strip()


class SemanticColumn(BaseModel):
    name: str
    data_type: str
    description: str
    aliases: list[str] = Field(default_factory=list)
    examples: list[str] = Field(default_factory=list)
    value_type: str | None = None
    pii: bool = False


class SemanticTable(BaseModel):
    name: str
    entity: str
    description: str
    aliases: list[str] = Field(default_factory=list)
    primary_key: str = "id"
    default_display_columns: list[str] = Field(default_factory=list)
    profile_columns: list[str] = Field(default_factory=list)
    columns: list[SemanticColumn] = Field(default_factory=list)

    def column(self, name: str) -> SemanticColumn | None:
        normalized = normalize_identifier(name)
        return next((column for column in self.columns if normalize_identifier(column.name) == normalized), None)


class SemanticJoin(BaseModel):
    from_table: str
    from_column: str
    to_table: str
    to_column: str
    description: str
    cardinality: str = "many_to_one"


class SemanticRule(BaseModel):
    name: str
    description: str
    applies_to: list[str] = Field(default_factory=list)


class SemanticCatalog(BaseModel):
    version: int = 1
    language: str = "fa"
    tables: list[SemanticTable] = Field(default_factory=list)
    joins: list[SemanticJoin] = Field(default_factory=list)
    rules: list[SemanticRule] = Field(default_factory=list)

    def table(self, name: str) -> SemanticTable | None:
        normalized = normalize_identifier(name)
        return next((table for table in self.tables if normalize_identifier(table.name) == normalized), None)

    def table_aliases(self) -> dict[str, list[str]]:
        return {table.name: table.aliases for table in self.tables}

    def resolve_table(self, text: str) -> SemanticTable | None:
        normalized = normalize_identifier(text)
        for table in self.tables:
            if normalize_identifier(table.name) in normalized:
                return table
            if any(normalize_identifier(alias) in normalized for alias in table.aliases):
                return table
        return None


class SemanticColumnSuggestion(BaseModel):
    name: str
    data_type: str
    display_name_fa: str
    description_fa: str
    aliases_fa: list[str] = Field(default_factory=list)
    value_type: str | None = None
    pii: bool = False
    confidence: float = 0.6
    confidence_reasons: list[str] = Field(default_factory=list)
    source: str = "heuristic"


class SemanticTableSuggestion(BaseModel):
    name: str
    entity: str
    display_name_fa: str
    description_fa: str
    aliases_fa: list[str] = Field(default_factory=list)
    primary_key: str = "id"
    default_display_columns: list[str] = Field(default_factory=list)
    profile_columns: list[str] = Field(default_factory=list)
    row_count: int = 0
    confidence: float = 0.6
    confidence_reasons: list[str] = Field(default_factory=list)
    review_required: bool = True
    columns: list[SemanticColumnSuggestion] = Field(default_factory=list)


class SemanticJoinSuggestion(BaseModel):
    from_table: str
    from_column: str
    to_table: str
    to_column: str
    description_fa: str
    cardinality: str = "many_to_one"
    confidence: float = 0.8


class SemanticBusinessTermSuggestion(BaseModel):
    term_fa: str
    aliases_fa: list[str] = Field(default_factory=list)
    maps_to: str
    description_fa: str
    confidence: float = 0.8
    review_required: bool = True


class SemanticValueMappingSuggestion(BaseModel):
    term_fa: str
    aliases_fa: list[str] = Field(default_factory=list)
    column: str
    value: str
    description_fa: str
    confidence: float = 0.8


class SemanticRuleSuggestion(BaseModel):
    name: str
    description_fa: str
    applies_to: list[str] = Field(default_factory=list)
    confidence: float = 0.8
    review_required: bool = True


class SemanticSuggestionSet(BaseModel):
    version: int = 1
    language: str = "fa"
    tenant_id: str
    source_fingerprint: str
    generated_at: str
    status: str = "draft"
    tables: list[SemanticTableSuggestion] = Field(default_factory=list)
    joins: list[SemanticJoinSuggestion] = Field(default_factory=list)
    business_terms: list[SemanticBusinessTermSuggestion] = Field(default_factory=list)
    value_mappings: list[SemanticValueMappingSuggestion] = Field(default_factory=list)
    rules: list[SemanticRuleSuggestion] = Field(default_factory=list)


class SemanticReviewRequest(BaseModel):
    target_type: str
    table: str
    column: str | None = None
    display_name_fa: str | None = None
    description_fa: str | None = None
    aliases_fa: list[str] | None = None
    entity: str | None = None
    value_type: str | None = None
    pii: bool | None = None
    approved: bool = True


class SemanticReviewResponse(BaseModel):
    status: str
    tenant_id: str
    target_type: str
    table: str
    column: str | None = None
    output_path: str | None = None
    message: str = ""


class SemanticValidationIssue(BaseModel):
    severity: str
    code: str
    message: str
    path: str = ""


class SemanticActivationResponse(BaseModel):
    status: str
    tenant_id: str
    source_fingerprint: str = ""
    active_catalog_path: str | None = None
    issues: list[SemanticValidationIssue] = Field(default_factory=list)
    tables: int = 0
    joins: int = 0
    rules: int = 0
    backup_path: str | None = None


class SemanticBenchmarkCaseResult(BaseModel):
    id: str
    question: str
    passed: bool
    failures: list[str] = Field(default_factory=list)
    elapsed_ms: float = 0.0


class SemanticBenchmarkSummary(BaseModel):
    total: int = 0
    passed: int = 0
    failed: int = 0
    pass_rate: float = 0.0
    avg_elapsed_ms: float = 0.0
    min_pass_rate: float = 95.0
    gate_status: str = "failed"


class SemanticBenchmarkResponse(BaseModel):
    status: str
    tenant_id: str
    source_fingerprint: str = ""
    summary: SemanticBenchmarkSummary
    results: list[SemanticBenchmarkCaseResult] = Field(default_factory=list)
    output_path: str | None = None
    latest_path: str | None = None


class SemanticSmokeTestCase(BaseModel):
    id: str
    table: str
    kind: str
    question: str
    execute: bool = False
    expected: dict = Field(default_factory=dict)


class SemanticSmokeTestGenerationResponse(BaseModel):
    status: str
    tenant_id: str
    source_fingerprint: str = ""
    cases: list[SemanticSmokeTestCase] = Field(default_factory=list)
    output_path: str | None = None


class SemanticSmokeTestResult(BaseModel):
    id: str
    table: str
    kind: str
    question: str
    passed: bool
    failures: list[str] = Field(default_factory=list)
    error_code: str = ""
    failure_stage: str = ""
    elapsed_ms: float = 0.0
    sql: str = ""
    response: dict = Field(default_factory=dict)


class SemanticSmokeTestRunSummary(BaseModel):
    total: int = 0
    passed: int = 0
    failed: int = 0
    pass_rate: float = 0.0
    avg_elapsed_ms: float = 0.0
    deterministic_sql: int = 0
    llm_sql: int = 0
    llm_required: int = 0
    lightweight_ready: int = 0
    lightweight_ready_rate: float = 0.0


class SemanticSmokeTestRunResponse(BaseModel):
    status: str
    tenant_id: str
    source_fingerprint: str = ""
    summary: SemanticSmokeTestRunSummary
    results: list[SemanticSmokeTestResult] = Field(default_factory=list)
    output_path: str | None = None
    latest_path: str | None = None


class LightweightGapSuggestion(BaseModel):
    question: str
    table: str = ""
    kind: str = ""
    error_code: str = ""
    recommended_action: str
    admin_hint: str
    technical_hint: str = ""
    suggested_review_payload: dict = Field(default_factory=dict)


class LightweightGapSuggestionResponse(BaseModel):
    status: str
    tenant_id: str
    total_cases: int = 0
    lightweight_ready_rate: float = 0.0
    gap_count: int = 0
    suggestions: list[LightweightGapSuggestion] = Field(default_factory=list)


class LightweightGapApplyResult(BaseModel):
    table: str
    column: str | None = None
    status: str
    message: str = ""
    payload: dict = Field(default_factory=dict)


class LightweightGapApplyResponse(BaseModel):
    status: str
    tenant_id: str
    requested: int = 0
    applied: int = 0
    failed: int = 0
    results: list[LightweightGapApplyResult] = Field(default_factory=list)
    validation_status: str | None = None
    validation_errors: int = 0
    validation_warnings: int = 0
    validation_issues: list[dict] = Field(default_factory=list)
    next_action: str = ""
    message: str = ""


class SemanticLifecycleStep(BaseModel):
    name: str
    status: str
    message: str = ""
    output_path: str | None = None
    details: dict = Field(default_factory=dict)


class SemanticLifecycleResponse(BaseModel):
    status: str
    tenant_id: str
    source_fingerprint: str = ""
    steps: list[SemanticLifecycleStep] = Field(default_factory=list)
    discovery: SchemaDiscoveryResponse | None = None
    activation: SemanticActivationResponse | None = None
    benchmark: SemanticBenchmarkResponse | None = None


class SemanticFreshnessResponse(BaseModel):
    status: str
    tenant_id: str
    current_fingerprint: str = ""
    stored_fingerprint: str = ""
    suggestions_fingerprint: str = ""
    active_catalog_exists: bool = False
    discovery_exists: bool = False
    suggestions_exist: bool = False
    tables_discovered: int = 0
    relationships_found: int = 0
    message: str = ""
    recommended_action: str = ""


class SemanticAutoUpdateResponse(BaseModel):
    status: str
    tenant_id: str
    action: str
    freshness_before: SemanticFreshnessResponse
    lifecycle: SemanticLifecycleResponse | None = None
    freshness_after: SemanticFreshnessResponse | None = None
    message: str = ""


class SemanticVersionInfo(BaseModel):
    version_id: str
    path: str
    created_at: str
    source_fingerprint: str = ""
    reason: str = ""
    tables: int = 0
    joins: int = 0
    rules: int = 0


class SemanticRollbackResponse(BaseModel):
    status: str
    tenant_id: str
    restored_version_id: str = ""
    active_catalog_path: str | None = None
    backup_path: str | None = None
    message: str = ""
