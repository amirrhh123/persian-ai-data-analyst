"""Tests for the Tiny Persian Intent Router contract."""

import pytest

from backend.router import (
    RouterPrediction,
    SIGNALS,
    SIGNAL_AMBIGUOUS,
    SIGNAL_MULTI_INTENT,
    SIGNAL_RANKING,
    SIGNAL_UNSAFE,
    V1_DOMAINS,
    is_domain,
    is_signal,
    validate_domain,
)


class TestExactDomainSet:
    def test_domain_set_has_exactly_seven_elements(self):
        assert len(V1_DOMAINS) == 7

    def test_all_expected_domains_present(self):
        expected = {"student", "employee", "school", "salary", "organization", "retirement", "generic_semantic"}
        assert V1_DOMAINS == expected

    def test_domain_is_frozenset(self):
        assert isinstance(V1_DOMAINS, frozenset)

    def test_is_domain_recognizes_all_domains(self):
        for d in V1_DOMAINS:
            assert is_domain(d) is True

    def test_is_domain_rejects_signals(self):
        for s in SIGNALS:
            assert is_domain(s) is False


class TestSignalDomainSeparation:
    def test_signal_constants_are_strings(self):
        assert isinstance(SIGNAL_UNSAFE, str)
        assert isinstance(SIGNAL_AMBIGUOUS, str)
        assert isinstance(SIGNAL_MULTI_INTENT, str)
        assert isinstance(SIGNAL_RANKING, str)

    def test_signals_are_not_domains(self):
        for s in SIGNALS:
            assert s not in V1_DOMAINS

    def test_domains_are_not_signals(self):
        for d in V1_DOMAINS:
            assert d not in SIGNALS

    def test_no_overlap_between_domains_and_signals(self):
        assert (V1_DOMAINS & SIGNALS) == frozenset()

    def test_signals_frozenset(self):
        assert isinstance(SIGNALS, frozenset)

    def test_is_signal_recognizes_all_signals(self):
        for s in SIGNALS:
            assert is_signal(s) is True

    def test_is_signal_rejects_domains(self):
        for d in V1_DOMAINS:
            assert is_signal(d) is False


class TestValidPrediction:
    def test_create_valid_prediction(self):
        p = RouterPrediction.create(
            domain="student", confidence=0.95,
            probabilities={"student": 0.95, "employee": 0.05},
            accepted=True, model_version="v1.0.0", latency_ms=12.5,
        )
        assert p.domain == "student"
        assert p.confidence == 0.95
        assert p.accepted is True
        assert p.model_version == "v1.0.0"
        assert p.latency_ms == 12.5

    def test_prediction_is_frozen(self):
        p = RouterPrediction(
            domain="student", confidence=0.5,
            probabilities={"student": 0.5, "employee": 0.5},
            accepted=False, model_version="v1.0.0", latency_ms=0.0,
        )
        with pytest.raises(Exception):
            p.domain = "employee"

    def test_probabilities_dict_immutable_on_frozen(self):
        p = RouterPrediction(
            domain="student", confidence=0.5,
            probabilities={"student": 0.5, "employee": 0.5},
            accepted=False, model_version="v1.0.0", latency_ms=0.0,
        )
        with pytest.raises(Exception):
            p.probabilities = {"student": 0.0}

    def test_probabilities_not_sum_to_one_is_allowed(self):
        p = RouterPrediction(
            domain="student", confidence=0.5,
            probabilities={"student": 0.6, "employee": 0.6},
            accepted=False, model_version="v1.0.0", latency_ms=0.0,
        )
        assert p.probabilities["student"] + p.probabilities["employee"] != 1.0

    def test_prediction_has_correct_types(self):
        p = RouterPrediction(
            domain="salary", confidence=0.8,
            probabilities={"salary": 1.0},
            accepted=True, model_version="v1.0.0", latency_ms=5.0,
        )
        assert isinstance(p.domain, str)
        assert isinstance(p.confidence, float)
        assert isinstance(p.probabilities, dict)
        assert isinstance(p.accepted, bool)
        assert isinstance(p.model_version, str)
        assert isinstance(p.latency_ms, float)


class TestInvalidDomain:
    def test_invalid_domain_raises(self):
        with pytest.raises(ValueError):
            RouterPrediction(
                domain="unknown", confidence=0.5,
                probabilities={"student": 0.5},
                accepted=False, model_version="v1.0.0", latency_ms=0.0,
            )

    def test_signal_as_domain_raises(self):
        with pytest.raises(ValueError):
            RouterPrediction(
                domain=SIGNAL_UNSAFE, confidence=0.5,
                probabilities={"student": 0.5},
                accepted=False, model_version="v1.0.0", latency_ms=0.0,
            )

    def test_validate_domain_passes_for_valid(self):
        for d in V1_DOMAINS:
            validate_domain(d)

    def test_empty_model_version_raises(self):
        with pytest.raises(ValueError):
            RouterPrediction(
                domain="student", confidence=0.5,
                probabilities={"student": 0.5},
                accepted=False, model_version="", latency_ms=0.0,
            )

    def test_whitespace_model_version_raises(self):
        with pytest.raises(ValueError):
            RouterPrediction(
                domain="student", confidence=0.5,
                probabilities={"student": 0.5},
                accepted=False, model_version="   ", latency_ms=0.0,
            )


class TestConfidenceBounds:
    def test_confidence_out_of_range_raises(self):
        with pytest.raises(ValueError):
            RouterPrediction(
                domain="student", confidence=-0.1,
                probabilities={"student": 1.0},
                accepted=False, model_version="v1.0.0", latency_ms=0.0,
            )
        with pytest.raises(ValueError):
            RouterPrediction(
                domain="student", confidence=1.5,
                probabilities={"student": 1.0},
                accepted=False, model_version="v1.0.0", latency_ms=0.0,
            )

    def test_confidence_zero_and_one_are_valid(self):
        p = RouterPrediction(
            domain="student", confidence=0.0,
            probabilities={"student": 0.0},
            accepted=False, model_version="v1.0.0", latency_ms=0.0,
        )
        assert p.confidence == 0.0
        p = RouterPrediction(
            domain="student", confidence=1.0,
            probabilities={"student": 1.0},
            accepted=True, model_version="v1.0.0", latency_ms=0.0,
        )
        assert p.confidence == 1.0


class TestInvalidProbabilityKey:
    def test_invalid_probability_key_raises(self):
        with pytest.raises(ValueError):
            RouterPrediction(
                domain="student", confidence=0.5,
                probabilities={"unknown_domain": 1.0},
                accepted=False, model_version="v1.0.0", latency_ms=0.0,
            )

    def test_signal_as_probability_key_raises(self):
        with pytest.raises(ValueError):
            RouterPrediction(
                domain="student", confidence=0.5,
                probabilities={SIGNAL_RANKING: 1.0},
                accepted=False, model_version="v1.0.0", latency_ms=0.0,
            )


class TestInvalidProbabilityValue:
    def test_probability_out_of_range_raises(self):
        with pytest.raises(ValueError):
            RouterPrediction(
                domain="student", confidence=0.5,
                probabilities={"student": -0.1},
                accepted=False, model_version="v1.0.0", latency_ms=0.0,
            )
        with pytest.raises(ValueError):
            RouterPrediction(
                domain="student", confidence=0.5,
                probabilities={"student": 1.5},
                accepted=False, model_version="v1.0.0", latency_ms=0.0,
            )

    def test_probability_zero_and_one_are_valid(self):
        p = RouterPrediction(
            domain="student", confidence=0.0,
            probabilities={"student": 0.0},
            accepted=False, model_version="v1.0.0", latency_ms=0.0,
        )
        assert p.probabilities["student"] == 0.0
        p = RouterPrediction(
            domain="student", confidence=1.0,
            probabilities={"student": 1.0},
            accepted=True, model_version="v1.0.0", latency_ms=0.0,
        )
        assert p.probabilities["student"] == 1.0


class TestNegativeLatency:
    def test_negative_latency_raises(self):
        with pytest.raises(ValueError):
            RouterPrediction(
                domain="student", confidence=0.5,
                probabilities={"student": 0.5},
                accepted=False, model_version="v1.0.0", latency_ms=-1.0,
            )

    def test_zero_and_positive_latency_is_valid(self):
        p = RouterPrediction(
            domain="student", confidence=0.5,
            probabilities={"student": 0.5},
            accepted=False, model_version="v1.0.0", latency_ms=0.0,
        )
        assert p.latency_ms == 0.0
        p = RouterPrediction(
            domain="student", confidence=0.5,
            probabilities={"student": 0.5},
            accepted=False, model_version="v1.0.0", latency_ms=100.0,
        )
        assert p.latency_ms == 100.0


class TestAcceptedWithInvalidDomain:
    def test_accepted_true_with_invalid_domain_raises(self):
        with pytest.raises(ValueError):
            RouterPrediction(
                domain="unsafe", confidence=0.5,
                probabilities={"student": 1.0},
                accepted=True, model_version="v1.0.0", latency_ms=0.0,
            )

    def test_accepted_true_with_valid_domain_is_valid(self):
        p = RouterPrediction(
            domain="student", confidence=0.9,
            probabilities={"student": 0.9},
            accepted=True, model_version="v1.0.0", latency_ms=0.0,
        )
        assert p.accepted is True
        assert p.domain == "student"


class TestTypeValidation:
    def test_accepted_non_bool_raises(self):
        with pytest.raises(TypeError):
            RouterPrediction(
                domain="student", confidence=0.5,
                probabilities={"student": 0.5},
                accepted=1, model_version="v1.0.0", latency_ms=0.0,
            )

    def test_confidence_bool_raises(self):
        with pytest.raises(TypeError):
            RouterPrediction(
                domain="student", confidence=True,
                probabilities={"student": 0.5},
                accepted=False, model_version="v1.0.0", latency_ms=0.0,
            )

    def test_latency_bool_raises(self):
        with pytest.raises(TypeError):
            RouterPrediction(
                domain="student", confidence=0.5,
                probabilities={"student": 0.5},
                accepted=False, model_version="v1.0.0", latency_ms=True,
            )

    def test_probability_value_bool_raises(self):
        with pytest.raises(TypeError):
            RouterPrediction(
                domain="student", confidence=0.5,
                probabilities={"student": True},
                accepted=False, model_version="v1.0.0", latency_ms=0.0,
            )

    def test_domain_non_string_raises(self):
        with pytest.raises(TypeError):
            RouterPrediction(
                domain=123, confidence=0.5,
                probabilities={"student": 0.5},
                accepted=False, model_version="v1.0.0", latency_ms=0.0,
            )

    def test_model_version_non_string_raises(self):
        with pytest.raises(TypeError):
            RouterPrediction(
                domain="student", confidence=0.5,
                probabilities={"student": 0.5},
                accepted=False, model_version=123, latency_ms=0.0,
            )


class TestImportExportContract:
    def test_all_public_symbols_importable(self):
        from backend.router import (
            RouterPrediction, V1_DOMAINS, SIGNAL_UNSAFE, SIGNAL_AMBIGUOUS,
            SIGNAL_MULTI_INTENT, SIGNAL_RANKING, SIGNALS,
            is_domain, is_signal, validate_domain,
        )
        assert callable(is_domain)
        assert callable(is_signal)
        assert callable(validate_domain)
        assert callable(RouterPrediction.create)

    def test___all__contains_expected_symbols(self):
        from backend.router import __all__
        expected = [
            "RouterPrediction", "V1_DOMAINS", "SIGNAL_UNSAFE", "SIGNAL_AMBIGUOUS",
            "SIGNAL_MULTI_INTENT", "SIGNAL_RANKING", "SIGNALS",
            "is_domain", "is_signal", "validate_domain",
        ]
        for name in expected:
            assert name in __all__

    def test_dataclass_has_all_six_fields(self):
        fields = set(RouterPrediction.__dataclass_fields__)
        assert fields == {"domain", "confidence", "probabilities", "accepted", "model_version", "latency_ms"}

    def test_frozen_via_setattr_raises(self):
        p = RouterPrediction(
            domain="student", confidence=0.5,
            probabilities={"student": 0.5},
            accepted=False, model_version="v1.0.0", latency_ms=0.0,
        )
        with pytest.raises(Exception):
            p.some_attr = "value"
