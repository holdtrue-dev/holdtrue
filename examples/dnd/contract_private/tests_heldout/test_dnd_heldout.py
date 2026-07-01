from hypothesis import given, strategies as st

from core import ability_modifier, attack_bonus, proficiency_bonus, spell_save_dc
from reference_impl import ability_modifier as r_modifier
from reference_impl import attack_bonus as r_attack
from reference_impl import proficiency_bonus as r_proficiency
from reference_impl import spell_save_dc as r_dc

_scores = st.integers(min_value=1, max_value=30)
_levels = st.integers(min_value=1, max_value=20)


@given(_scores)
def test_modifier_agrees(score: int) -> None:
    assert ability_modifier(score) == r_modifier(score)


@given(_levels)
def test_proficiency_agrees(level: int) -> None:
    assert proficiency_bonus(level) == r_proficiency(level)


@given(_scores, _levels)
def test_dc_agrees(score: int, level: int) -> None:
    assert spell_save_dc(score, level) == r_dc(score, level)


@given(_scores, _levels, st.booleans())
def test_attack_agrees(score: int, level: int, proficient: bool) -> None:
    assert attack_bonus(score, level, proficient) == r_attack(score, level, proficient)
