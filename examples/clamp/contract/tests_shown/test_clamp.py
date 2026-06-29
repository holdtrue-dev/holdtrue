"""Shown property test. The implementer may read this.

Checks only the range, not the exact value. The value is pinned by the contract
and the held-out test, so the answer is not in the shown tests.
"""
from hypothesis import given, strategies as st

from core import clamp

ints = st.integers(min_value=-1000, max_value=1000)


@given(ints, ints, ints)
def test_result_in_range(x, lo, hi):
    if lo <= hi:
        result = clamp(x, lo, hi)
        assert lo <= result <= hi
