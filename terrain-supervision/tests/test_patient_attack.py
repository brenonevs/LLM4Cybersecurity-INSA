"""Deterministic reproduction of the patient reputation-building attack."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import run


def _case(warmup_count, label):
    payload = dict(run.PATIENT_ATTACK_PAYLOADS)[label]
    return run.patient_attack_case(warmup_count, label, payload)


def test_critical_attack_is_detected_but_six_prior_observations_allow_email():
    blocked = _case(5, "critical-instruction")
    allowed = _case(6, "critical-instruction")

    assert (blocked["result"], blocked["weight"]) == ("unfavorable", 2.0)
    assert blocked["decisions"]["send_email"] is False
    assert blocked["decisions"]["restart_equipment"] is True
    assert (allowed["alpha"], allowed["beta"], allowed["trust"]) == (7.0, 3.0, 0.7)
    assert allowed["decisions"] == {
        "send_email": True,
        "write_file": True,
        "restart_equipment": True,
    }


def test_external_email_attack_needs_five_prior_observations_to_allow_email():
    blocked = _case(4, "external-email")
    allowed = _case(5, "external-email")

    assert (blocked["result"], blocked["weight"]) == ("unfavorable", 1.5)
    assert blocked["decisions"]["send_email"] is False
    assert (allowed["alpha"], allowed["beta"]) == (6.0, 2.5)
    assert allowed["trust"] > 0.70
    assert allowed["decisions"]["send_email"] is True


def test_decay_reduces_the_trust_available_to_a_patient_attacker():
    payload = dict(run.PATIENT_ATTACK_PAYLOADS)["critical-instruction"]
    without_decay = run.patient_attack_case(10, "critical-instruction", payload)
    with_decay = run.patient_attack_case(10, "critical-instruction", payload, 0.85)

    assert without_decay["trust"] > with_decay["trust"]
    assert without_decay["decisions"]["send_email"] is True
    assert with_decay["decisions"]["send_email"] is False


def test_recent_risk_blocks_a_patient_attacker_despite_a_high_long_term_trust():
    payload = dict(run.PATIENT_ATTACK_PAYLOADS)["critical-instruction"]

    result = run.patient_attack_case(
        10, "critical-instruction", payload, recent_risk=True)

    assert result["trust"] > 0.70
    assert result["recent_risk"] == 1.0
    assert result["decisions"] == {
        "send_email": False,
        "write_file": False,
        "restart_equipment": False,
    }


def test_low_and_medium_attacks_are_recorded_but_do_not_activate_recent_risk():
    payloads = dict(run.PATIENT_ATTACK_PAYLOADS)

    low = run.patient_attack_case(
        10, "low-directive", payloads["low-directive"], recent_risk=True)
    medium = run.patient_attack_case(
        10, "medium-override", payloads["medium-override"], recent_risk=True)

    assert (low["result"], low["severity"], low["weight"], low["recent_risk"]) == (
        "unfavorable", "low", 0.5, 0.0)
    assert (medium["result"], medium["severity"], medium["weight"], medium["recent_risk"]) == (
        "unfavorable", "medium", 1.0, 0.0)
    assert low["decisions"]["send_email"] is True
    assert medium["decisions"]["send_email"] is True


def test_recent_risk_requires_ten_new_credited_favorable_observations_to_clear():
    payload = dict(run.PATIENT_ATTACK_PAYLOADS)["critical-instruction"]
    protection = run.ScoreConfiance(authorization=True, recent_risk=True)
    protection.nouvel_episode()

    for index in range(1, 7):
        protection.observer(run.Fragment(
            f"warm-up {index}", evidences=[run._patient_warmup_evidence(index)]))
        protection.reinitialiser()
    protection.observer(run.Fragment("attack", evidences=[
        run._patient_attack_evidence("critical-instruction", payload)]))
    assert protection.risque_recent(run.PATIENT_ATTACK_SOURCE, run.PATIENT_ATTACK_KIND) == 1.0
    assert protection.verifier("send_email", {}, "externe") is not None

    for index in range(7, 17):
        protection.reinitialiser()
        protection.observer(run.Fragment(
            f"recovery {index}", evidences=[run._patient_warmup_evidence(index)]))

    assert protection.risque_recent(run.PATIENT_ATTACK_SOURCE, run.PATIENT_ATTACK_KIND) == 0.0
    assert protection.verifier("send_email", {}, "externe") is None


def test_repeated_new_strong_incidents_escalate_one_source_risk_by_half():
    payload = dict(run.PATIENT_ATTACK_PAYLOADS)["critical-instruction"]
    protection = run.ScoreConfiance(authorization=True, recent_risk=True)
    protection.nouvel_episode()

    first = run._patient_attack_evidence("critical-instruction", payload)
    protection.observer(run.Fragment("first attack", evidences=[first]))
    assert protection.risque_recent(run.PATIENT_ATTACK_SOURCE, run.PATIENT_ATTACK_KIND) == 1.0

    protection.reinitialiser()
    second = run.SourceEvidence(
        first.reference, first.content + " Do it immediately.")
    protection.observer(run.Fragment("second attack", evidences=[second]))
    assert protection.risque_recent(run.PATIENT_ATTACK_SOURCE, run.PATIENT_ATTACK_KIND) == 1.5

    # Replaying the exact same content version is not a new incident.
    protection.reinitialiser()
    protection.observer(run.Fragment("replay", evidences=[second]))
    assert protection.risque_recent(run.PATIENT_ATTACK_SOURCE, run.PATIENT_ATTACK_KIND) == 1.5


def test_recidivism_campaign_escalates_each_new_incident_and_keeps_tools_blocked():
    payload = dict(run.PATIENT_ATTACK_PAYLOADS)["critical-instruction"]

    result = run.patient_recidivism_case(
        warmup_count=3, label="critical-instruction", payload=payload,
        occurrences=3)

    assert [row["risk_after"] for row in result["rows"]] == [1.0, 1.5, 2.0]
    assert [row["email_allowed"] for row in result["rows"]] == [False, False, False]


def test_recidivism_campaign_applies_partial_recovery_between_incidents():
    payload = dict(run.PATIENT_ATTACK_PAYLOADS)["critical-instruction"]

    result = run.patient_recidivism_case(
        warmup_count=3, label="critical-instruction", payload=payload,
        occurrences=2, recovery_between=2)

    assert [row["risk_after"] for row in result["rows"]] == [1.0, 1.3]

def test_patient_recovery_releases_sensitive_tools_only_after_recent_risk_clears():
    payload = dict(run.PATIENT_ATTACK_PAYLOADS)["external-email"]
    blocked = run.patient_recovery_case(
        10, "external-email", payload, 9, recent_risk=True)
    allowed = run.patient_recovery_case(
        10, "external-email", payload, 10, recent_risk=True)

    assert blocked["recent_risk"] > 0.0
    assert blocked["decisions"]["send_email"] is False
    assert allowed["recent_risk"] == 0.0
    assert allowed["decisions"] == {
        "send_email": True,
        "write_file": True,
        "restart_equipment": True,
    }
