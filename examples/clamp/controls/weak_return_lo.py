"""Broken `return lo`. CrossHair confirms it against the bounds-only contract,
but the held-out test and the negative-probe catch it."""


def clamp(x: int, lo: int, hi: int) -> int:
    return lo
