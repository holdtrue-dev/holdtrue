"""A correct implementation. The two derived functions are built from the two
building blocks, the way the intent describes them: spell_save_dc and attack_bonus
call ability_modifier and proficiency_bonus instead of repeating the formulas."""


def ability_modifier(score: int) -> int:
    return (score - 10) // 2


def proficiency_bonus(level: int) -> int:
    return 2 + (level - 1) // 4


def spell_save_dc(score: int, level: int) -> int:
    return 8 + proficiency_bonus(level) + ability_modifier(score)


def attack_bonus(score: int, level: int, proficient: bool) -> int:
    bonus = ability_modifier(score)
    if proficient:
        bonus += proficiency_bonus(level)
    return bonus
