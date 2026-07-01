# Intent: poker

Rank five-card poker hands. A card has a rank (2 through 10, then jack, queen, king, ace, with ace high) and a suit. A hand is five distinct cards.

- **is flush**: whether all five cards share a suit.
- **is straight**: whether the five ranks are five in a row. Ace is high only, so 10-J-Q-K-A is a straight but A-2-3-4-5 is not.
- **hand category**: the best category the hand makes: high card, pair, two pair, three of a kind, straight, flush, full house, four of a kind, or straight flush.
- **compare**: given two hands, which one wins. Return 1 if the first hand is better, -1 if the second is better, and 0 if they tie. Hands are compared by category first, then by the ranks that make them up.

Four functions over a shared card type.
