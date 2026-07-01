"""A correct implementation, written a little differently from the reference oracle:
the knight move is checked as "the smaller gap is one and the larger gap is two"
rather than as a chain of ands, so the held-out test compares two independent
derivations of the same rule."""


def square_index(file: int, rank: int) -> int:
    return rank * 8 + file


def is_light_square(file: int, rank: int) -> bool:
    return (file + rank) % 2 != 0


def king_distance(f1: int, r1: int, f2: int, r2: int) -> int:
    return max(abs(f1 - f2), abs(r1 - r2))


def is_knight_move(f1: int, r1: int, f2: int, r2: int) -> bool:
    df, dr = abs(f1 - f2), abs(r1 - r2)
    return min(df, dr) == 1 and max(df, dr) == 2
