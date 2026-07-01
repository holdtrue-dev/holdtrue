"""A buggy implementation. Three functions are right; add_seconds forgets to wrap
around midnight, so a time plus a delta can land at or past a full day. The contract
requires the result to stay in 0..86399 and to equal the wrapped value, so the verdict
is FAILED and names add_seconds."""


def to_seconds(h: int, m: int, s: int) -> int:
    return h * 3600 + m * 60 + s


def add_seconds(sec: int, delta: int) -> int:
    # bug: no wrap, so the result can fall outside a single day
    return sec + delta


def is_am(sec: int) -> bool:
    return sec < 43200


def minutes_between(a: int, b: int) -> int:
    return ((b - a) % 86400) // 60
