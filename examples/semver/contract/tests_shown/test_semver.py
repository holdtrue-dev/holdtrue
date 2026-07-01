from hypothesis import given, settings, strategies as st

from core import compare, max_satisfying, satisfies, satisfies_all
from models import Constraint, Op, Version

settings.register_profile("holdtrue", max_examples=40, deadline=None)
settings.load_profile("holdtrue")

_versions = st.builds(
    Version,
    major=st.integers(min_value=0, max_value=3),
    minor=st.integers(min_value=0, max_value=5),
    patch=st.integers(min_value=0, max_value=5),
)
_constraints = st.builds(Constraint, op=st.sampled_from(list(Op)), version=_versions)


def _expected_satisfies(v: Version, c: Constraint) -> bool:
    cmp = compare(v, c.version)
    return (
        cmp == 0 if c.op == Op.EQ else
        cmp >= 0 if c.op == Op.GTE else
        cmp > 0 if c.op == Op.GT else
        cmp <= 0 if c.op == Op.LTE else
        cmp < 0 if c.op == Op.LT else
        (v.major == c.version.major and cmp >= 0) if c.op == Op.CARET else
        (v.major == c.version.major and v.minor == c.version.minor and cmp >= 0)
    )


@given(_versions, _versions)
def test_compare(a: Version, b: Version) -> None:
    ta = (a.major, a.minor, a.patch)
    tb = (b.major, b.minor, b.patch)
    assert compare(a, b) == ((ta > tb) - (ta < tb))


@given(_versions, _constraints)
def test_satisfies(v: Version, c: Constraint) -> None:
    assert satisfies(v, c) == _expected_satisfies(v, c)


@given(_versions, st.lists(_constraints, max_size=4))
def test_satisfies_all(v: Version, constraints: list[Constraint]) -> None:
    assert satisfies_all(v, constraints) == all(satisfies(v, c) for c in constraints)


@given(st.lists(_versions, max_size=6), _constraints)
def test_max_satisfying(versions: list[Version], c: Constraint) -> None:
    r = max_satisfying(versions, c)
    ok = [v for v in versions if satisfies(v, c)]
    if not ok:
        assert r is None
    else:
        assert r is not None and satisfies(r, c) and r in versions
        assert all(compare(r, v) >= 0 for v in ok)
