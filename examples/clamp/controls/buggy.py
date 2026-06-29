"""Buggy clamp. Expected: FAILED. CrossHair finds a counterexample."""


def clamp(x: int, lo: int, hi: int) -> int:
    return lo + 1
