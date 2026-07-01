"""The shared types for the poker contract: a rank, a suit, a card, and the hand
categories in increasing strength. pydantic validates a card on construction, so an
out-of-range rank cannot be built. CrossHair cannot reason over these, so the
functions are enforced at runtime, not proven."""
from __future__ import annotations

from enum import Enum, IntEnum

from pydantic import BaseModel


class Suit(str, Enum):
    CLUBS = "C"
    DIAMONDS = "D"
    HEARTS = "H"
    SPADES = "S"


class Rank(IntEnum):
    TWO = 2
    THREE = 3
    FOUR = 4
    FIVE = 5
    SIX = 6
    SEVEN = 7
    EIGHT = 8
    NINE = 9
    TEN = 10
    JACK = 11
    QUEEN = 12
    KING = 13
    ACE = 14


class Category(IntEnum):
    HIGH_CARD = 0
    PAIR = 1
    TWO_PAIR = 2
    THREE_OF_A_KIND = 3
    STRAIGHT = 4
    FLUSH = 5
    FULL_HOUSE = 6
    FOUR_OF_A_KIND = 7
    STRAIGHT_FLUSH = 8


class Card(BaseModel):
    rank: Rank
    suit: Suit
