"""Offline tests for LLM-assisted Persian alias enrichment (accuracy work #2)."""

import shutil
import tempfile

import backend.semantic.alias_enrichment as module
from backend.semantic.alias_enrichment import AliasEnrichmentService
from backend.semantic.models import (
    SemanticColumnSuggestion,
    SemanticSuggestionSet,
    SemanticTableSuggestion,
)


def _tmp():
    return tempfile.mkdtemp(prefix="alias_enrich_")


def _column(name, data_type="character varying", pk=False, pii=False, samples=None, aliases=None):
    # Suggestion-level columns carry no PK flag; key columns are filtered by name.
    return SemanticColumnSuggestion(
        name=name,
        data_type=data_type,
        display_name_fa=name.replace("_", " "),
        description_fa=name.replace("_", " "),
        aliases_fa=list(aliases or [name]),
        pii=pii,
        sample_values=[type("SV", (), {"value": v})() for v in (samples or [])],
    )


def _suggestions(tables):
    from datetime import datetime

    return SemanticSuggestionSet(
        tenant_id="t",
        source_fingerprint="fp1",
        generated_at=datetime.now().isoformat(timespec="seconds"),
        tables=tables,
        joins=[],
        business_terms=[],
        value_mappings=[],
        rules=[],
    )


def _table(name, columns):
    return SemanticTableSuggestion(
        name=name,
        entity=name,
        display_name_fa=name,
        description_fa=name,
        primary_key="id",
        columns=columns,
    )


class _FakeLLM:
    def __init__(self, responses=None, connected=True):
        import asyncio

        self.prompts = []
        self.responses = responses or {}
        self.connected = connected
        self.loop = asyncio

        class _Settings:
            llm_enabled = True
            alias_max_columns_per_run = 40

        self.settings = _Settings()

    async def is_connected(self):
        return self.connected

    async def chat(self, prompt):
        self.prompts.append(prompt)
        for needle, response in self.responses.items():
            if needle in prompt:
                return response
        return "[]"


def _patch_llm(monkeypatch, fake):
    monkeypatch.setattr(module, "llm_service", fake)


# ----------------------------------------------------------------------
# Sanitization / parsing
# ----------------------------------------------------------------------

def test_parse_aliases_happy_path():
    text = 'Here: ["شهر", "شهرستان", «استان»] done'
    assert AliasEnrichmentService._parse_aliases(text) == ["شهر", "شهرستان", "استان"]


def test_parse_aliases_rejects_english_and_junk():
    text = '["city", "SELECT *", "ab", "' + "x" * 50 + '", "شهر"]'
    assert AliasEnrichmentService._parse_aliases(text) == ["شهر"]


def test_parse_aliases_survives_garbage():
    assert AliasEnrichmentService._parse_aliases("model said no") == []


def test_pk_pii_and_id_columns_not_enrichable():
    assert not AliasEnrichmentService._is_enrichable(_column("id", pk=True))
    assert not AliasEnrichmentService._is_enrichable(_column("national_id"))
    assert not AliasEnrichmentService._is_enrichable(_column("school_id"))
    assert AliasEnrichmentService._is_enrichable(_column("status", samples=["active"]))


# ----------------------------------------------------------------------
# Enrichment flow with fakes
# ----------------------------------------------------------------------

def test_enrichment_merges_llm_aliases(monkeypatch):
    tmp = _tmp()
    fake = _FakeLLM(responses={"requests": '["حالت", "وضعیت رکورد"]'})
    _patch_llm(monkeypatch, fake)
    service = AliasEnrichmentService()
    monkeypatch.setattr(service, "_cache_path", lambda tenant: f"{tmp}/cache.json")

    suggestions = _suggestions(
        [_table("requests", [_column("status", samples=["active"], aliases=["وضعیت"])])]
    )
    result, stats = _run(service.enrich_suggestions("t", suggestions))

    assert stats["prompted"] == 1
    merged = result.tables[0].columns[0].aliases_fa
    assert "حالت" in merged and "وضعیت رکورد" in merged and "وضعیت" in merged


def test_second_run_hits_cache_without_prompting(monkeypatch):
    tmp = _tmp()
    fake = _FakeLLM(responses={"requests": '["حالت"]'})
    _patch_llm(monkeypatch, fake)
    service = AliasEnrichmentService()
    monkeypatch.setattr(service, "_cache_path", lambda tenant: f"{tmp}/cache.json")

    first = _suggestions(
        [_table("requests", [_column("status", samples=["active"], aliases=["وضعیت"])])]
    )
    _run(service.enrich_suggestions("t", first))
    prompts_after_first = len(fake.prompts)

    fresh = _suggestions(
        [_table("requests", [_column("status", samples=["active"], aliases=["وضعیت"])])]
    )
    result2, stats2 = _run(service.enrich_suggestions("t", fresh))
    assert len(fake.prompts) == prompts_after_first
    assert stats2["prompted"] == 0
    assert "حالت" in result2.tables[0].columns[0].aliases_fa


def test_budget_limits_prompts_per_run(monkeypatch):
    tmp = _tmp()
    fake = _FakeLLM(responses={"alpha": '["الف"]', "beta": '["ب"]'})
    _patch_llm(monkeypatch, fake)
    service = AliasEnrichmentService()
    service.settings.alias_max_columns_per_run = 1
    monkeypatch.setattr(service, "_cache_path", lambda tenant: f"{tmp}/cache.json")
    suggestions = _suggestions(
        [
            _table(
                "requests",
                [
                    _column("alpha", samples=["a"], aliases=["آلفا"]),
                    _column("beta", samples=["b"], aliases=["بتا"]),
                ],
            )
        ]
    )
    _result, stats = _run(service.enrich_suggestions("t", suggestions))
    assert stats["prompted"] == 1


def test_bad_llm_output_is_graceful_noop(monkeypatch):
    tmp = _tmp()
    fake = _FakeLLM(responses={"requests": "I cannot answer that"})
    _patch_llm(monkeypatch, fake)
    service = AliasEnrichmentService()
    monkeypatch.setattr(service, "_cache_path", lambda tenant: f"{tmp}/cache.json")
    suggestions = _suggestions(
        [_table("requests", [_column("status", samples=["active"], aliases=["وضعیت"])])]
    )
    result, stats = _run(service.enrich_suggestions("t", suggestions))
    assert stats["aliases_added"] == 0
    assert result.tables[0].columns[0].aliases_fa == ["وضعیت"]


def test_unreachable_llm_skips_entirely(monkeypatch):
    tmp = _tmp()
    fake = _FakeLLM(connected=False)
    _patch_llm(monkeypatch, fake)
    service = AliasEnrichmentService()
    monkeypatch.setattr(service, "_cache_path", lambda t: f"{tmp}/c.json")
    suggestions = _suggestions([_table("r", [_column("status", samples=["a"])])])

    result, stats = _run(service.enrich_suggestions("t", suggestions))
    assert stats["enabled"] is False
    assert stats["reason"] == "llm_unreachable"
    assert result.tables[0].columns[0].aliases_fa == ["status"]


def _run(coro):
    import asyncio

    return asyncio.run(coro)
