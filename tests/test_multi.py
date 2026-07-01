"""Multi-function contracts end to end: several functions in one module, each proven
on its own, with the overall verdict the weakest of them. A correct module earns
GUARANTEED across every function; a module with one broken function earns FAILED and
names the function that broke, while the others still read GUARANTEED. Unsandboxed and
without mutation, like test_loop and test_pydantic."""
from pathlib import Path

import pytest

from holdtrue.classify import FAILED, GUARANTEED
from holdtrue.report import build_report
from holdtrue.verify import load_manifest, run_verification

ROOT = Path(__file__).resolve().parents[1]

# (example, the function the buggy control breaks)
CASES = [
    ("dnd", "attack_bonus"),
    ("chess", "king_distance"),
    ("clock", "add_seconds"),
]


def _verify(example: str, impl: str):
    project = ROOT / "examples" / example
    m = load_manifest(project, "contract/manifest.yaml")
    results, cls = run_verification(project, project / "controls" / impl, m,
                                    sandbox_on=False, mutation=False)
    return m, results, cls


@pytest.mark.parametrize("example,_broken", CASES)
def test_correct_is_guaranteed(example: str, _broken: str) -> None:
    _, _, cls = _verify(example, "correct.py")
    assert cls.classification == GUARANTEED
    assert cls.requires_human_code_review is False


@pytest.mark.parametrize("example,broken", CASES)
def test_buggy_is_failed_and_names_the_function(example: str, broken: str) -> None:
    _, _, cls = _verify(example, "buggy.py")
    assert cls.classification == FAILED
    assert cls.failed_subtype == "buggy-implementation"
    # the deciding check is prefixed with the function that actually broke, not one
    # dragged down by a shared property test
    assert cls.deciding_check.startswith(broken)
    # the other functions in the same module are still individually proven
    assert any(r.startswith(broken) and "FAILED" in r for r in cls.reasons)
    assert any("GUARANTEED" in r for r in cls.reasons)


def test_normalize_accepts_both_decorator_shapes() -> None:
    # nested (mirrors the single-function schema, and what the author writes) and flat
    # both normalise to a flat `decorators` key, so neither shape crashes downstream.
    from holdtrue.verify import _normalize_manifest
    nested = _normalize_manifest({"functions": [
        {"function": "f", "signature": "f(x: int) -> int",
         "checks": {"crosshair": {"decorators": ["@deal.raises()"]}}}]})
    flat = _normalize_manifest({"functions": [
        {"function": "f", "signature": "f(x: int) -> int",
         "decorators": ["@deal.raises()"]}]})
    assert nested["functions"][0]["decorators"] == ["@deal.raises()"]
    assert flat["functions"][0]["decorators"] == ["@deal.raises()"]


def test_report_renders_all_signatures() -> None:
    m, results, cls = _verify("dnd", "correct.py")
    rep = build_report(m, "correct.py", results, cls, sandboxed=False)
    assert len(rep["signatures"]) == 4
    assert "ability_modifier" in rep["signature"]
