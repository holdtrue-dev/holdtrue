"""A buggy implementation. Three functions are right; compare only looks at the hand
category and ignores the tie-break ranks, so two hands of the same category always tie
even when one clearly wins (two high-card hands, say). The runtime contract only pins
the category-level sign, so it passes; the held-out oracle, which knows the full
ordering, catches it, and the verdict is FAILED, naming compare."""
from __future__ import annotations

from collections import Counter

from models import Card, Category


def is_flush(cards: list[Card]) -> bool:
    return all(c.suit == cards[0].suit for c in cards)


def is_straight(cards: list[Card]) -> bool:
    ranks = sorted(int(c.rank) for c in cards)
    return len(set(ranks)) == 5 and ranks[-1] - ranks[0] == 4


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


def compare(a: list[Card], b: list[Card]) -> int:
    # bug: category only, ignores the tie-break ranks
    ca, cb = int(hand_category(a)), int(hand_category(b))
    return (ca > cb) - (ca < cb)
