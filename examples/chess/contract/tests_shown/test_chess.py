from hypothesis import given, strategies as st

from core import is_knight_move, is_light_square, king_distance, square_index

_coord = st.integers(min_value=0, max_value=7)


@given(_coord, _coord)
def test_square_index(file: int, rank: int) -> None:
    assert square_index(file, rank) == rank * 8 + file


@given(_coord, _coord)
def test_is_light_square(file: int, rank: int) -> None:
    assert is_light_square(file, rank) == ((file + rank) % 2 == 1)


@given(_coord, _coord, _coord, _coord)
def test_king_distance(f1: int, r1: int, f2: int, r2: int) -> None:
    assert king_distance(f1, r1, f2, r2) == max(abs(f1 - f2), abs(r1 - r2))


@given(_coord, _coord, _coord, _coord)
def test_is_knight_move(f1: int, r1: int, f2: int, r2: int) -> None:
    df, dr = abs(f1 - f2), abs(r1 - r2)
    assert is_knight_move(f1, r1, f2, r2) == ((df == 1 and dr == 2) or (df == 2 and dr == 1))
