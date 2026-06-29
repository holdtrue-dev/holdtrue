"""Reference oracle. Author-side, used by the held-out test only."""


def abs(x: int) -> int:
    if x >= 0:
        return x
    return -x
