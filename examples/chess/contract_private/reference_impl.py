"""Reference oracle. Author-side, used by the held-out differential test only."""


def square_index(file: int, rank: int) -> int:
    return rank * 8 + file


def is_light_square(file: int, rank: int) -> bool:
    return (file + rank) % 2 == 1


def king_distance(f1: int, r1: int, f2: int, r2: int) -> int:
    return max(abs(f1 - f2), abs(r1 - r2))


def is_knight_move(f1: int, r1: int, f2: int, r2: int) -> bool:
    df = abs(f1 - f2)
    dr = abs(r1 - r2)
    return (df == 1 and dr == 2) or (df == 2 and dr == 1)
