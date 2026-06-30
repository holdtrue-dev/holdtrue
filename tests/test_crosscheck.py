"""Second-author cross-check: the parts that hold without an LLM.

`added_anything` decides whether the merge actually closed a gap; `render_contract`
is what the second author's contract is summarised as for the merge. The live second
author and merge step are exercised manually."""
from holdtrue import crosscheck


def _m(decos, must_reject=None, axes=None):
    return {
        "signature": "clamp(x: int, lo: int, hi: int) -> int",
        "checks": {"crosshair": {"decorators": decos}},
        "negative_probe": {"must_reject": must_reject or []},
        "interrogated_axes": axes or [],
    }


def test_added_anything_detects_a_new_postcondition():
    old = _m(["@deal.ensure(lambda x, r: lo <= r <= hi)"])
    new = _m(["@deal.ensure(lambda x, r: lo <= r <= hi)",
              "@deal.ensure(lambda x, r: r == min(max(x, lo), hi))"])
    assert crosscheck.added_anything(old, new)


def test_added_anything_detects_a_new_axis_or_probe():
    base = _m(["@deal.ensure(lambda x, r: True)"], must_reject=["return lo"], axes=["range"])
    more_axis = _m(["@deal.ensure(lambda x, r: True)"], must_reject=["return lo"],
                   axes=["range", "exact value"])
    more_probe = _m(["@deal.ensure(lambda x, r: True)"], must_reject=["return lo", "return hi"],
                    axes=["range"])
    assert crosscheck.added_anything(base, more_axis)
    assert crosscheck.added_anything(base, more_probe)


def test_added_anything_false_when_identical():
    m = _m(["@deal.ensure(lambda x, r: True)"], must_reject=["return lo"], axes=["range"])
    assert not crosscheck.added_anything(m, dict(m))


def test_render_contract_lists_signature_decorators_and_axes():
    out = crosscheck.render_contract(_m(["@deal.ensure(lambda x, r: r >= 0)"], axes=["sign"]))
    assert "clamp(x: int, lo: int, hi: int) -> int" in out
    assert "@deal.ensure(lambda x, r: r >= 0)" in out
    assert "- sign" in out
