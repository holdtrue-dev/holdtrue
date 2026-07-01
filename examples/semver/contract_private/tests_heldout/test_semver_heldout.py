from hypothesis import given, settings, strategies as st

from core import compare, max_satisfying, satisfies, satisfies_all
from models import Constraint, Op, Version
from reference_impl import compare as r_compare
from reference_impl import max_satisfying as r_max
from reference_impl import satisfies as r_satisfies
from reference_impl import satisfies_all as r_satisfies_all

settings.register_profile("holdtrue", max_examples=40, deadline=None)
settings.load_profile("holdtrue")

_versions = st.builds(
    Version,
    major=st.integers(min_value=0, max_value=3),
    minor=st.integers(min_value=0, max_value=5),
    patch=st.integers(min_value=0, max_value=5),
)
_constraints = st.builds(Constraint, op=st.sampled_from(list(Op)), version=_versions)


@given(_versions, _versions)
def test_compare_agrees(a: Version, b: Version) -> None:
    assert compare(a, b) == r_compare(a, b)


@given(_versions, _constraints)
def test_satisfies_agrees(v: Version, c: Constraint) -> None:
    assert satisfies(v, c) == r_satisfies(v, c)


@given(_versions, st.lists(_constraints, max_size=4))
def test_satisfies_all_agrees(v: Version, constraints: list[Constraint]) -> None:
    assert satisfies_all(v, constraints) == r_satisfies_all(v, constraints)


@given(st.lists(_versions, max_size=6), _constraints)
def test_max_satisfying_agrees(versions: list[Version], c: Constraint) -> None:
    assert max_satisfying(versions, c) == r_max(versions, c)
