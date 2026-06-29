"""Held-out test. The implementer never sees this.

Compares the implementation to the reference oracle. Passing the shown test but
failing this means an overfit or a bug.
"""
from hypothesis import given, strategies as st

from core import clamp
from reference_impl import clamp as reference

ints = st.integers(min_value=-1000, max_value=1000)


@given(ints, ints, ints)
def test_matches_reference(x, lo, hi):
    if lo <= hi:
        assert clamp(x, lo, hi) == reference(x, lo, hi)
