"""Held-out test. The implementer never sees this.

Compares the implementation to the reference oracle. Passing the shown test but
failing this means an overfit or a bug.
"""
from hypothesis import given, strategies as st

from core import abs
from reference_impl import abs as reference

ints = st.integers(min_value=-1000, max_value=1000)


@given(ints)
def test_matches_reference(x):
    assert abs(x) == reference(x)
