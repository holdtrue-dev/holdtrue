"""The loop must produce the right verdict on each control implementation.

Runs unsandboxed: CI runners often disallow the user namespaces bwrap needs, and
the sandbox is the anti-tamper boundary, not part of the verification logic.
"""
from pathlib import Path

from holdtrue.classify import FAILED, GUARANTEED, UNGUARANTEED
from holdtrue.verify import load_manifest, run_verification

ROOT = Path(__file__).resolve().parents[1]
CLAMP = ROOT / "examples" / "clamp"


def _verify(impl: str, manifest: str = "contract/manifest.yaml", mutation: bool = True):
    m = load_manifest(CLAMP, manifest)
    _, cls = run_verification(CLAMP, CLAMP / "controls" / impl, m,
                              sandbox_on=False, mutation=mutation)
    return cls


def test_correct_impl_is_guaranteed():
    cls = _verify("correct.py")
    assert cls.classification == GUARANTEED
    assert cls.deciding_check == "CHK-symbolic"
    assert cls.requires_human_code_review is False


def test_buggy_impl_fails_with_counterexample():
    cls = _verify("buggy.py", mutation=False)
    assert cls.classification == FAILED
    assert cls.failed_subtype == "buggy-implementation"


def test_weak_contract_is_downgraded_by_negative_probe():
    # A correct implementation, but the bounds-only contract is too weak: the
    # negative-probe must refuse the guarantee even though CrossHair confirms.
    cls = _verify("correct.py", manifest="contract/manifest_weak.yaml", mutation=False)
    assert cls.classification == UNGUARANTEED
    assert "negprobe" in cls.deciding_check.lower()


def test_terse_correct_is_guaranteed_without_mutation_backing():
    # The terse form has no mutable nodes, so mutation is NA. A sound proof plus
    # the negative-probe still earn GUARANTEED; mutation is not a gate.
    cls = _verify("correct_terse.py")
    assert cls.classification == GUARANTEED
    assert cls.deciding_check == "CHK-symbolic"
