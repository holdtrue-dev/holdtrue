from hypothesis import given, strategies as st

from core import is_knight_move, is_light_square, king_distance, square_index
from reference_impl import is_knight_move as r_knight
from reference_impl import is_light_square as r_light
from reference_impl import king_distance as r_king
from reference_impl import square_index as r_index

_coord = st.integers(min_value=0, max_value=7)


@given(_coord, _coord)
def test_index_agrees(file: int, rank: int) -> None:
    assert square_index(file, rank) == r_index(file, rank)


@given(_coord, _coord)
def test_light_agrees(file: int, rank: int) -> None:
    assert is_light_square(file, rank) == r_light(file, rank)


@given(_coord, _coord, _coord, _coord)
def test_king_agrees(f1: int, r1: int, f2: int, r2: int) -> None:
    assert king_distance(f1, r1, f2, r2) == r_king(f1, r1, f2, r2)


@given(_coord, _coord, _coord, _coord)
def test_knight_agrees(f1: int, r1: int, f2: int, r2: int) -> None:
    assert is_knight_move(f1, r1, f2, r2) == r_knight(f1, r1, f2, r2)
