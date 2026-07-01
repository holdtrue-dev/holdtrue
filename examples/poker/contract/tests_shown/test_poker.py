from hypothesis import given, settings, strategies as st

from core import compare, hand_category, is_flush, is_straight
from models import Card, Category, Rank, Suit

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
def test_is_flush(cards: list[Card]) -> None:
    assert is_flush(cards) == (len({c.suit for c in cards}) == 1)


@given(_h)
def test_is_straight(cards: list[Card]) -> None:
    ranks = {int(c.rank) for c in cards}
    assert is_straight(cards) == (len(ranks) == 5 and max(ranks) - min(ranks) == 4)


@given(_h)
def test_hand_category(cards: list[Card]) -> None:
    cat = hand_category(cards)
    assert is_flush(cards) == (cat in (Category.FLUSH, Category.STRAIGHT_FLUSH))
    assert is_straight(cards) == (cat in (Category.STRAIGHT, Category.STRAIGHT_FLUSH))


@given(_h, _h)
def test_compare(a: list[Card], b: list[Card]) -> None:
    r = compare(a, b)
    assert r in (-1, 0, 1)
    if hand_category(a) != hand_category(b):
        assert r == ((hand_category(a) > hand_category(b))
                     - (hand_category(a) < hand_category(b)))
