"""The verdict logic, including the ENFORCED tier that widens the domain past what
CrossHair can prove. Pure: built from fabricated check results, no prover."""
from holdtrue.classify import (ENFORCED, FAILED, GUARANTEED, UNGUARANTEED, classify)
from holdtrue.engine import CheckResult


def _r(kind, status, detail="ok", **kw):
    return CheckResult(check_id=f"CHK-{kind}", kind=kind, status=status, detail=detail, **kw)


def _results(crosshair, *, probe="pass", types="pass", shown="pass", heldout="pass"):
    return {
        "types": _r("types", types),
        "crosshair": _r("crosshair", crosshair, counterexample="x=1" if crosshair == "refuted" else None),
        "hypothesis_shown": _r("hypothesis_shown", shown),
        "hypothesis_heldout": _r("hypothesis_heldout", heldout),
        "negative_probe": _r("negative_probe", probe),
    }


def test_proven_and_strong_is_guaranteed():
    cls = classify("INT", _results("confirmed"))
    assert cls.classification == GUARANTEED
    assert cls.requires_human_code_review is False


def test_unproven_but_enforced_is_enforced():
    # CrossHair could not exhaust (a string/list/loop shape), but the contract is
    # runtime-enforced, non-vacuous, and clean over samples.
    cls = classify("INT", _results("unconfirmed"))
    assert cls.classification == ENFORCED
    assert cls.requires_human_code_review is False
    assert any("runtime-enforced" in r for r in cls.reasons)


def test_unproven_and_weak_contract_is_unguaranteed():
    # Negative-probe fails: the contract is too weak, so no proof means just sampled.
    cls = classify("INT", _results("unconfirmed", probe="fail"))
    assert cls.classification == UNGUARANTEED


def test_proven_but_weak_contract_is_unguaranteed():
    cls = classify("INT", _results("confirmed", probe="fail"))
    assert cls.classification == UNGUARANTEED


def test_unproven_without_held_out_samples_is_not_enforced():
    # No held-out evidence (na) means it cannot reach ENFORCED; it is just sampled.
    cls = classify("INT", _results("unconfirmed", heldout="na"))
    assert cls.classification == UNGUARANTEED


def test_counterexample_is_failed():
    cls = classify("INT", _results("refuted"))
    assert cls.classification == FAILED
    assert cls.failed_subtype == "buggy-implementation"
