"""The pydantic / ENFORCED path end to end: a rich-type contract CrossHair cannot
prove still earns a verdict, runtime-enforced and clean over samples, and a wrong
implementation is still caught. Unsandboxed, like test_loop."""
from pathlib import Path

from holdtrue.classify import ENFORCED, FAILED
from holdtrue.verify import load_manifest, run_verification

ROOT = Path(__file__).resolve().parents[1]
CHECKOUT = ROOT / "examples" / "checkout"


def _verify(impl: str):
    m = load_manifest(CHECKOUT, "contract/manifest.yaml")
    _, cls = run_verification(CHECKOUT, CHECKOUT / "controls" / impl, m,
                              sandbox_on=False, mutation=False)
    return cls


def test_checkout_correct_is_enforced():
    cls = _verify("correct.py")
    assert cls.classification == ENFORCED
    assert cls.requires_human_code_review is False
    assert any("runtime-enforced" in r for r in cls.reasons)


def test_checkout_buggy_is_failed():
    cls = _verify("buggy.py")
    assert cls.classification == FAILED
    assert cls.failed_subtype == "buggy-implementation"
