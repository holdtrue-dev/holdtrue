"""Reference oracle. Author-side, used by the held-out differential test only.

Each function is written out in full from the rules, independently of the
implementation, so the held-out test compares two separate derivations rather than
one derivation against itself.
"""


def ability_modifier(score: int) -> int:
    return (score - 10) // 2


def proficiency_bonus(level: int) -> int:
    return 2 + (level - 1) // 4


def spell_save_dc(score: int, level: int) -> int:
    return 8 + (2 + (level - 1) // 4) + ((score - 10) // 2)


def attack_bonus(score: int, level: int, proficient: bool) -> int:
    bonus = (score - 10) // 2
    if proficient:
        bonus += 2 + (level - 1) // 4
    return bonus
