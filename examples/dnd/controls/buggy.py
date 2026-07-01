"""A buggy implementation. Three functions are right; attack_bonus adds the
proficiency bonus even when the character is not proficient. The contract pins that
axis, so the verdict is FAILED and names attack_bonus as the function that broke."""


def ability_modifier(score: int) -> int:
    return (score - 10) // 2


def proficiency_bonus(level: int) -> int:
    return 2 + (level - 1) // 4


def spell_save_dc(score: int, level: int) -> int:
    return 8 + proficiency_bonus(level) + ability_modifier(score)


def attack_bonus(score: int, level: int, proficient: bool) -> int:
    # bug: always adds the proficiency bonus, ignoring `proficient`
    return ability_modifier(score) + proficiency_bonus(level)
