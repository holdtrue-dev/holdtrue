"""Reference oracle. Author-side, used by the held-out differential test only.

The category-by-category logic and the full tie-break ordering live here; the runtime
contract pins the flush and straight relationships and the shape of compare, and this
oracle pins the rest.
"""
from __future__ import annotations

from collections import Counter

from models import Card, Category


def is_flush(cards: list[Card]) -> bool:
    return len({c.suit for c in cards}) == 1


def is_straight(cards: list[Card]) -> bool:
    ranks = {int(c.rank) for c in cards}
    return len(ranks) == 5 and max(ranks) - min(ranks) == 4


def hand_category(cards: list[Card]) -> Category:
    counts = sorted(Counter(c.rank for c in cards).values(), reverse=True)
    flush = is_flush(cards)
    straight = is_straight(cards)
    if straight and flush:
        return Category.STRAIGHT_FLUSH
    if counts[0] == 4:
        return Category.FOUR_OF_A_KIND
    if counts[0] == 3 and counts[1] == 2:
        return Category.FULL_HOUSE
    if flush:
        return Category.FLUSH
    if straight:
        return Category.STRAIGHT
    if counts[0] == 3:
        return Category.THREE_OF_A_KIND
    if counts[0] == 2 and counts[1] == 2:
        return Category.TWO_PAIR
    if counts[0] == 2:
        return Category.PAIR
    return Category.HIGH_CARD


def _key(cards: list[Card]) -> tuple[int, list[int]]:
    counts = Counter(int(c.rank) for c in cards)
    # order the ranks by how many of them there are, then by rank, both descending
    ordered = sorted(counts, key=lambda r: (counts[r], r), reverse=True)
    tiebreak = [r for r in ordered for _ in range(counts[r])]
    return int(hand_category(cards)), tiebreak


def compare(a: list[Card], b: list[Card]) -> int:
    ka, kb = _key(a), _key(b)
    return (ka > kb) - (ka < kb)
