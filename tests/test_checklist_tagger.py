"""
tests/test_checklist_tagger.py

Unit tests for the deterministic PA checklist tagger in evidence_gatherer.py.

These tests do NOT require a live HAPI server or OpenAI API key.
They test _build_checklist() directly with hand-crafted FHIR resource dicts.

Run with:
    pytest tests/test_checklist_tagger.py -v
"""

from __future__ import annotations

import sys
from pathlib import Path

# Add src/ to path for import without pip install -e .
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pytest

from prior_auth_copilot.nodes.evidence_gatherer import _build_checklist


# ---------------------------------------------------------------------------
# Minimal FHIR resource factories
# ---------------------------------------------------------------------------


def _condition(snomed_code: str, rid: str = "cond-1") -> dict:
    return {
        "resourceType": "Condition",
        "id": rid,
        "code": {
            "coding": [{"system": "http://snomed.info/sct", "code": snomed_code}]
        },
    }


def _medication(rxnorm_code: str, rid: str = "med-1") -> dict:
    return {
        "resourceType": "MedicationRequest",
        "id": rid,
        "code": {
            "coding": [{"system": "http://www.nlm.nih.gov/research/umls/rxnorm", "code": rxnorm_code}]
        },
    }


def _procedure(snomed_code: str, date: str, rid: str = "proc-1") -> dict:
    return {
        "resourceType": "Procedure",
        "id": rid,
        "code": {
            "coding": [{"system": "http://snomed.info/sct", "code": snomed_code}]
        },
        "performedDateTime": date,
    }


def _observation(loinc_code: str, value: float, rid: str = "obs-1") -> dict:
    return {
        "resourceType": "Observation",
        "id": rid,
        "code": {
            "coding": [{"system": "http://loinc.org", "code": loinc_code}]
        },
        "valueQuantity": {"value": value, "unit": "{score}"},
    }


# ---------------------------------------------------------------------------
# Tests — complete evidence path
# ---------------------------------------------------------------------------


class TestCompleteEvidence:
    """All 4 required criteria met; radiculopathy bonus criterion also met."""

    @pytest.fixture
    def result(self):
        conditions = [
            _condition("279039007", "cond-lbp"),
            _condition("57054005", "cond-radiculopathy"),
        ]
        procedures = [
            _procedure("36048009", "2023-01-10", "proc-pt1"),
            _procedure("36048009", "2023-02-15", "proc-pt2"),  # 36 days later
        ]
        medications = [_medication("197803", "med-ibu")]
        observations = [_observation("72514-3", 7.0, "obs-pain")]
        checklist, tags_map = _build_checklist(conditions, procedures, medications, observations)
        return checklist, tags_map

    def test_all_required_criteria_met(self, result):
        checklist, _ = result
        required = [i for i in checklist.items if "Optional" not in i.criterion]
        assert all(i.met for i in required), [i for i in required if not i.met]

    def test_radiculopathy_bonus_met(self, result):
        checklist, _ = result
        neuro = next(i for i in checklist.items if "radiculopathy" in i.criterion.lower())
        assert neuro.met

    def test_all_met_property(self, result):
        checklist, _ = result
        assert checklist.all_met

    def test_tags_map_populated(self, result):
        _, tags_map = result
        assert any("lbp_diagnosis" in tags for tags in tags_map.values())
        assert any("nsaid_prescribed" in tags for tags in tags_map.values())
        assert any("physical_therapy" in tags for tags in tags_map.values())
        assert any("pain_score" in tags for tags in tags_map.values())

    def test_evidence_refs_populated(self, result):
        checklist, _ = result
        lbp_item = next(i for i in checklist.items if "Low back pain" in i.criterion)
        assert "Condition/cond-lbp" in lbp_item.evidence_refs


# ---------------------------------------------------------------------------
# Tests — missing conservative path (no NSAID, no PT)
# ---------------------------------------------------------------------------


class TestMissingConservative:
    @pytest.fixture
    def result(self):
        conditions = [_condition("279039007", "cond-lbp")]
        checklist, tags_map = _build_checklist(conditions, [], [], [])
        return checklist, tags_map

    def test_lbp_criterion_met(self, result):
        checklist, _ = result
        lbp = next(i for i in checklist.items if "Low back pain" in i.criterion)
        assert lbp.met

    def test_nsaid_criterion_not_met(self, result):
        checklist, _ = result
        nsaid = next(i for i in checklist.items if "NSAID" in i.criterion)
        assert not nsaid.met

    def test_pt_criterion_not_met(self, result):
        checklist, _ = result
        pt = next(i for i in checklist.items if "Physical therapy" in i.criterion)
        assert not pt.met

    def test_all_met_is_false(self, result):
        checklist, _ = result
        assert not checklist.all_met

    def test_met_count(self, result):
        checklist, _ = result
        assert checklist.met_count == 1  # only LBP


# ---------------------------------------------------------------------------
# Tests — short conservative path (1 PT session, gap < 28 days)
# ---------------------------------------------------------------------------


class TestShortConservative:
    @pytest.fixture
    def result(self):
        conditions = [_condition("279039007")]
        procedures = [_procedure("36048009", "2023-01-10", "proc-pt1")]  # only 1 session
        medications = [_medication("197803")]
        observations = [_observation("72514-3", 7.0)]
        checklist, tags_map = _build_checklist(conditions, procedures, medications, observations)
        return checklist, tags_map

    def test_pt_criterion_not_met_one_session(self, result):
        checklist, _ = result
        pt = next(i for i in checklist.items if "Physical therapy" in i.criterion)
        assert not pt.met
        assert "1 PT session(s)" in pt.note

    def test_other_criteria_met(self, result):
        checklist, _ = result
        lbp = next(i for i in checklist.items if "Low back pain" in i.criterion)
        nsaid = next(i for i in checklist.items if "NSAID" in i.criterion)
        pain = next(i for i in checklist.items if "Pain severity" in i.criterion)
        assert lbp.met and nsaid.met and pain.met


# ---------------------------------------------------------------------------
# Tests — two PT sessions but gap < 28 days
# ---------------------------------------------------------------------------


class TestPTGapTooShort:
    @pytest.fixture
    def result(self):
        conditions = [_condition("279039007")]
        procedures = [
            _procedure("36048009", "2023-01-10", "proc-pt1"),
            _procedure("36048009", "2023-01-25", "proc-pt2"),  # 15 days gap — too short
        ]
        medications = [_medication("197803")]
        observations = [_observation("72514-3", 7.0)]
        checklist, _ = _build_checklist(conditions, procedures, medications, observations)
        return checklist

    def test_pt_criterion_not_met_short_gap(self, result):
        pt = next(i for i in result.items if "Physical therapy" in i.criterion)
        assert not pt.met
        assert "gap = 15 days" in pt.note


# ---------------------------------------------------------------------------
# Tests — empty state (nothing retrieved)
# ---------------------------------------------------------------------------


class TestEmptyState:
    def test_all_criteria_not_met(self):
        checklist, tags_map = _build_checklist([], [], [], [])
        assert not checklist.all_met
        assert checklist.met_count == 0
        assert tags_map == {}
