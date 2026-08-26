"""Offline tests for the hard onboarding readiness gate (accuracy work #5)."""

from typing import Any, Dict, List

import pytest

import backend.database.onboarding_gate as gate_module
from backend.database.models import SchemaDiscoveryResponse
from backend.database.onboarding_gate import OnboardingGateService


class _Fake:
    def __init__(self, **kwargs):
        for key, value in kwargs.items():
            setattr(self, key, value)


def _discovery_ok():
    return SchemaDiscoveryResponse(
        tenant_id="t",
        tables_discovered=3,
        relationships_found=2,
        inferred_relationships=1,
        fingerprint="fp",
        status="success",
    )


def _benchmark(pass_rate):
    return _Fake(summary=_Fake(total=20, passed=round(20 * pass_rate / 100), failed=0, pass_rate=pass_rate))


def _suggestions():
    return _Fake(tables=[], source_fingerprint="fp")


def _patch_world(monkeypatch, *, benchmark_pass_rate, activation_status, discovery_fail=False, smoke_fail=False, gaps=0):
    calls: List[str] = []

    from backend.database.discovery_service import schema_discovery_service as discovery
    from backend.database.sync_service import schema_sync_service
    from backend.semantic.suggestion_service import semantic_suggestion_service as suggestions_svc
    from backend.semantic.alias_enrichment import alias_enrichment_service
    from backend.semantic.activation_service import semantic_activation_service
    from backend.semantic.benchmark_service import semantic_benchmark_service
    from backend.semantic.lightweight_gap_service import lightweight_gap_service
    from backend.semantic.smoke_test_service import semantic_smoke_test_service
    from backend.database.onboarding_service import database_onboarding_service
    from backend.value_index.service import value_index_service

    monkeypatch.setattr(
        discovery,
        "sync_discovery",
        lambda **kw: (
            calls.append("discovery"),
            _Fake(status="error: x") if discovery_fail else _discovery_ok(),
        )[-1],
    )

    monkeypatch.setattr(
        schema_sync_service,
        "sync_schema",
        lambda tenant: (calls.append("schema_cache"), _Fake(status="success"))[-1],
    )

    monkeypatch.setattr(
        suggestions_svc,
        "sync",
        lambda tenant_id=None: (calls.append("suggestions"), (_suggestions(), "path"))[1],
    )
    monkeypatch.setattr(suggestions_svc, "save", lambda s: "path")

    async def fake_enrich(tenant, suggs, max_prompts=None, **kw):
        calls.append("alias_enrichment")
        return suggs, {"enabled": False, "reason": "llm_disabled"}

    monkeypatch.setattr(alias_enrichment_service, "enrich_suggestions", fake_enrich)

    monkeypatch.setattr(database_onboarding_service, "load_snapshot", lambda tenant: _Fake(tables=[]))

    def fake_sync(snapshot, **kw):
        calls.append("value_index")
        return _Fake(entries=[]), "path"

    monkeypatch.setattr(value_index_service, "sync", fake_sync)
    monkeypatch.setattr(value_index_service, "deep_refresh", lambda idx, snap: (_Fake(entries=[]), {}))
    monkeypatch.setattr(value_index_service, "save", lambda idx: "path")

    async def fake_suggest(tenant, limit=None):
        calls.append("gap_suggest")
        return _Fake(suggestions=[object() for _ in range(gaps)])

    async def fake_apply(tenant, limit=None, validate_after=False):
        calls.append("gap_apply")
        return {"applied": min(gaps, 3), "failed": 0}

    monkeypatch.setattr(lightweight_gap_service, "suggest", fake_suggest)
    monkeypatch.setattr(lightweight_gap_service, "apply_suggestions", fake_apply)

    def fake_smoke_sync(tenant_id=None):
        calls.append("smoke_cases")
        if smoke_fail:
            return _Fake(status="error")
        return _Fake(status="success", cases=[object(), object(), object()])

    monkeypatch.setattr(semantic_smoke_test_service, "sync", fake_smoke_sync)

    async def fake_benchmark(**kw):
        calls.append("benchmark")
        return _benchmark(benchmark_pass_rate)

    monkeypatch.setattr(semantic_benchmark_service, "run", fake_benchmark)

    activation_calls = []

    def fake_activate(tenant, force=False):
        activation_calls.append({"force": force})
        calls.append("activation")
        return _Fake(status=activation_status)

    monkeypatch.setattr(semantic_activation_service, "activate", fake_activate)

    return calls, activation_calls


@pytest.fixture
def service(monkeypatch):
    svc = OnboardingGateService()
    monkeypatch.setattr(svc, "_save", lambda tenant, report: f"{tenant}/gate.json")
    return svc


def test_ready_when_benchmark_passes_and_activation_ok(service, monkeypatch):
    calls, activation_calls = _patch_world(
        monkeypatch, benchmark_pass_rate=97.0, activation_status="activated"
    )
    report = _run(service.run("t"))

    assert report.verdict == "ready"
    assert report.pass_rate == 97.0
    assert not activation_calls[0]["force"]  # never force through the gate
    # Ordering contract: benchmark strictly before activation.
    assert calls.index("benchmark") < calls.index("activation")


def test_blocked_below_threshold_never_activates(service, monkeypatch):
    calls, activation_calls = _patch_world(
        monkeypatch, benchmark_pass_rate=80.0, activation_status="activated"
    )
    report = _run(service.run("t"))

    assert report.verdict == "blocked"
    assert "activation" not in calls  # hard block
    assert report.blockers and report.next_actions


def test_failed_discovery_short_circuits(service, monkeypatch):
    calls, _ = _patch_world(monkeypatch, benchmark_pass_rate=100.0, activation_status="activated", discovery_fail=True)
    report = _run(service.run("t"))
    assert report.verdict == "failed"
    assert "suggestions" not in calls


def test_smoke_failure_blocks_without_benchmark(service, monkeypatch):
    calls, _ = _patch_world(
        monkeypatch, benchmark_pass_rate=100.0, activation_status="activated", smoke_fail=True
    )
    report = _run(service.run("t"))
    assert report.verdict == "blocked"
    assert "benchmark" not in calls


def test_auto_fix_runs_only_when_requested(service, monkeypatch):
    calls_on, _ = _patch_world(monkeypatch, benchmark_pass_rate=97.0, activation_status="activated", gaps=4)
    _run(service.run("t", auto_fix=True))
    assert "gap_suggest" in calls_on and "gap_apply" in calls_on

    calls_off, _ = _patch_world(monkeypatch, benchmark_pass_rate=97.0, activation_status="activated", gaps=4)
    _run(service.run("t", auto_fix=False))
    assert "gap_suggest" not in calls_off


def test_report_persisted_to_tenant_artifact(monkeypatch):
    written: Dict[str, Any] = {}
    svc = OnboardingGateService()

    def fake_save(tenant, report):
        written[tenant] = report.dict_for_file()
        return f"{tenant}/gate.json"

    monkeypatch.setattr(svc, "_save", fake_save)
    _patch_world(monkeypatch, benchmark_pass_rate=97.0, activation_status="activated")
    _run(svc.run("t"))

    assert "t" in written
    payload = written["t"]
    assert payload["verdict"] == "ready" and payload["steps"]

    # load_last_report reads the same shape back.
    class _P:
        def exists(self):
            return True

        def read_text(self, encoding):
            import json

            return json.dumps(payload)

    monkeypatch.setattr(svc, "report_path", lambda tenant: _P())
    loaded = svc.load_last_report("t")
    assert loaded["verdict"] == "ready"


def _run(coro):
    import asyncio

    return asyncio.run(coro)
