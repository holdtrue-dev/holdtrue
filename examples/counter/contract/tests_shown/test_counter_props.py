"""Shown property test: functional properties of Counter, no model comparison.

The implementer may read this.  Checks only invariants that should hold on any
correct implementation, not internal state.
"""
from hypothesis import given
import hypothesis.strategies as st

from core import Counter

maxes = st.integers(min_value=0, max_value=50)
ops = st.integers(min_value=0, max_value=20)


@given(maxes, ops)
def test_up_stays_in_bounds(maximum: int, n: int) -> None:
    c = Counter(maximum)
    for _ in range(n):
        c.up()
    assert 0 <= c.value() <= maximum


@given(maxes)
def test_reset_goes_to_zero(maximum: int) -> None:
    c = Counter(maximum)
    for _ in range(maximum + 1):
        c.up()
    c.reset()
    assert c.value() == 0


@given(maxes)
def test_initial_value_is_zero(maximum: int) -> None:
    assert Counter(maximum).value() == 0
