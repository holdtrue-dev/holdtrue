"""Correct clamp. Expected: GUARANTEED.

Written with ifs so it has nodes to mutate; `return max(lo, min(x, hi))` has none.
"""


def clamp(x: int, lo: int, hi: int) -> int:
    if x < lo:
        return lo
    if x > hi:
        return hi
    return x
