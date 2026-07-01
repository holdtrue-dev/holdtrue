from hypothesis import given, settings, strategies as st

from core import compare, hand_category, is_flush, is_straight
from models import Card, Rank, Suit
from reference_impl import compare as r_compare
from reference_impl import hand_category as r_category
from reference_impl import is_flush as r_flush
from reference_impl import is_straight as r_straight

settings.register_profile("holdtrue", max_examples=40, deadline=None)
settings.load_profile("holdtrue")

_SUITS = list(Suit)


@st.composite
def _hand(draw: st.DrawFn) -> list[Card]:
    idx = draw(st.lists(st.integers(min_value=0, max_value=51),
                        min_size=5, max_size=5, unique=True))
    return [Card(rank=Rank(2 + i // 4), suit=_SUITS[i % 4]) for i in idx]


_h = _hand()


@given(_h)
def test_is_flush_agrees(cards: list[Card]) -> None:
    assert is_flush(cards) == r_flush(cards)


@given(_h)
def test_is_straight_agrees(cards: list[Card]) -> None:
    assert is_straight(cards) == r_straight(cards)


@given(_h)
def test_hand_category_agrees(cards: list[Card]) -> None:
    assert hand_category(cards) == r_category(cards)


@given(_h, _h)
def test_compare_agrees(a: list[Card], b: list[Card]) -> None:
    assert compare(a, b) == r_compare(a, b)
