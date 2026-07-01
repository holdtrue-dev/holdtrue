from hypothesis import given, strategies as st

from core import ability_modifier, attack_bonus, proficiency_bonus, spell_save_dc

_scores = st.integers(min_value=1, max_value=30)
_levels = st.integers(min_value=1, max_value=20)


@given(_scores)
def test_ability_modifier(score: int) -> None:
    assert ability_modifier(score) == (score - 10) // 2


@given(_levels)
def test_proficiency_bonus(level: int) -> None:
    assert proficiency_bonus(level) == 2 + (level - 1) // 4


@given(_scores, _levels)
def test_spell_save_dc(score: int, level: int) -> None:
    assert spell_save_dc(score, level) == 8 + (2 + (level - 1) // 4) + ((score - 10) // 2)


@given(_scores, _levels, st.booleans())
def test_attack_bonus(score: int, level: int, proficient: bool) -> None:
    expected = (score - 10) // 2 + ((2 + (level - 1) // 4) if proficient else 0)
    assert attack_bonus(score, level, proficient) == expected
