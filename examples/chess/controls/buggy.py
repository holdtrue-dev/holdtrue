"""A buggy implementation. Three functions are right; king_distance returns the
Manhattan distance (the sum of the gaps) instead of the Chebyshev distance (the
larger gap), so it is wrong on any diagonal move. The contract pins the exact value,
so the verdict is FAILED and names king_distance."""


def square_index(file: int, rank: int) -> int:
    return rank * 8 + file


def is_light_square(file: int, rank: int) -> bool:
    return (file + rank) % 2 == 1


def king_distance(f1: int, r1: int, f2: int, r2: int) -> int:
    # bug: sum of the gaps (Manhattan) instead of the larger gap (Chebyshev)
    return abs(f1 - f2) + abs(r1 - r2)


def is_knight_move(f1: int, r1: int, f2: int, r2: int) -> bool:
    return (abs(f1 - f2), abs(r1 - r2)) in {(1, 2), (2, 1)}
