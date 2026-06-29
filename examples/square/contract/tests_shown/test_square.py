"""Shown property test. The implementer may read this.

Checks only the sign, not the exact value. The value is pinned by the contract
and the held-out test, so the answer is not in the shown tests.
"""
from hypothesis import given, strategies as st

from core import square

ints = st.integers(min_value=-1000, max_value=1000)


@given(ints)
def test_result_non_negative(x):
    assert square(x) >= 0
