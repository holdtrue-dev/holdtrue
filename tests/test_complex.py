"""The big, rich-type multi-function contracts end to end. These are ENFORCED, not
proven: the functions take pydantic models, lists, and enums that CrossHair cannot
exhaust, so the deal contracts are enforced at runtime and checked against a held-out
oracle. billing is mixed: two pure-integer helpers are proven GUARANTEED and two
document-level functions are ENFORCED. A buggy control breaks exactly one function so
the per-function verdict names it. Unsandboxed and without mutation, like test_multi."""
from pathlib import Path

import pytest

from holdtrue.classify import ENFORCED, FAILED, GUARANTEED
from holdtrue.verify import load_manifest, run_verification

ROOT = Path(__file__).resolve().parents[1]

# (example, the function the buggy control breaks)
CASES = [
    ("scheduler", "merge"),
    ("billing", "apply_rate"),
    ("poker", "compare"),
    ("semver", "satisfies_all"),
]


def _verify(example: str, impl: str):
    project = ROOT / "examples" / example
    m = load_manifest(project, "contract/manifest.yaml")
    _, cls = run_verification(project, project / "controls" / impl, m,
                              sandbox_on=False, mutation=False)
    return cls


@pytest.mark.parametrize("example,_broken", CASES)
def test_correct_is_enforced(example: str, _broken: str) -> None:
    cls = _verify(example, "correct.py")
    assert cls.classification == ENFORCED
    assert cls.requires_human_code_review is False
    if example == "billing":
        # mixed tier: the two pure-integer helpers are proven; the two document-level
        # functions, which take pydantic models, are enforced. Overall is the weakest.
        joined = "\n".join(cls.reasons)
        assert "apply_rate: " + GUARANTEED in joined
        assert "nonneg: " + GUARANTEED in joined
        assert "settle: " + ENFORCED in joined


@pytest.mark.parametrize("example,broken", CASES)
def test_buggy_is_failed_and_names_the_function(example: str, broken: str) -> None:
    cls = _verify(example, "buggy.py")
    assert cls.classification == FAILED
    assert cls.deciding_check.startswith(broken)
