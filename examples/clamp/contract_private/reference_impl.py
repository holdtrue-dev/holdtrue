"""Reference oracle. Author-side, used by the held-out test only."""


def clamp(x, lo, hi):
    return min(max(x, lo), hi)
