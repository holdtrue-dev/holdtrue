"""Correct clamp, terse form. CrossHair proves it; it has no mutable nodes, so
mutation is NA. Expected: GUARANTEED on the proof plus the negative-probe.

This is the form a separate-context LLM implementer wrote from the contract alone.
"""


def clamp(x: int, lo: int, hi: int) -> int:
    return min(max(x, lo), hi)
