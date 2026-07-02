"""Stateful Hypothesis test: run sequences of Counter operations and assert invariants.

The implementer may read this test.  It imports the implementation from `core`
(the module holdtrue writes the implementation to during verification).
"""
from hypothesis.stateful import RuleBasedStateMachine, initialize, rule, invariant
from hypothesis import settings, HealthCheck
import hypothesis.strategies as st

from core import Counter


class CounterMachine(RuleBasedStateMachine):
    """A shadow model that mirrors what the Counter should do, then checks."""

    @initialize(maximum=st.integers(min_value=0, max_value=20))
    def init(self, maximum: int) -> None:
        self._max = maximum
        self._model = 0
        self._counter = Counter(maximum)

    @rule()
    def up(self) -> None:
        self._counter.up()
        if self._model < self._max:
            self._model += 1

    @rule()
    def down(self) -> None:
        self._counter.down()
        if self._model > 0:
            self._model -= 1

    @rule()
    def reset(self) -> None:
        self._counter.reset()
        self._model = 0

    @invariant()
    def value_in_bounds(self) -> None:
        v = self._counter.value()
        assert 0 <= v <= self._max, (
            f"value {v} is outside [0, {self._max}]")

    @invariant()
    def value_matches_model(self) -> None:
        assert self._counter.value() == self._model, (
            f"counter {self._counter.value()} != model {self._model}")


# Expose as a TestCase so pytest discovers it.
TestCounter = CounterMachine.TestCase
