"""Reference oracle. Author-side, used by the held-out differential test only."""


def to_seconds(h: int, m: int, s: int) -> int:
    return h * 3600 + m * 60 + s


def add_seconds(sec: int, delta: int) -> int:
    return (sec + delta) % 86400


def is_am(sec: int) -> bool:
    return sec < 43200


def minutes_between(a: int, b: int) -> int:
    return ((b - a) % 86400) // 60
