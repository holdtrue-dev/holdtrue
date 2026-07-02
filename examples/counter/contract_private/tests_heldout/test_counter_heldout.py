"""Held-out differential test. The implementer never sees this.

Compares the implementation against the reference oracle over a sampled sequence
of operations to catch implementations that pass the shown tests by luck.
"""
from hypothesis.stateful import RuleBasedStateMachine, initialize, rule, invariant
import hypothesis.strategies as st

from core import Counter as Impl
from reference_impl import Counter as Oracle


class DifferentialMachine(RuleBasedStateMachine):
    @initialize(maximum=st.integers(min_value=0, max_value=30))
    def init(self, maximum: int) -> None:
        self._impl = Impl(maximum)
        self._oracle = Oracle(maximum)

    @rule()
    def up(self) -> None:
        self._impl.up()
        self._oracle.up()

    @rule()
    def down(self) -> None:
        self._impl.down()
        self._oracle.down()

    @rule()
    def reset(self) -> None:
        self._impl.reset()
        self._oracle.reset()

    @invariant()
    def agrees_with_oracle(self) -> None:
        assert self._impl.value() == self._oracle.value(), (
            f"impl={self._impl.value()} oracle={self._oracle.value()}")


TestCounterDifferential = DifferentialMachine.TestCase
