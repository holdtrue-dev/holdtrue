class Counter:
    def __init__(self, maximum: int) -> None:
        self._max = maximum
        self._value = 0

    def up(self) -> None:
        if self._value < self._max:
            self._value += 1

    def down(self) -> None:
        if self._value > 0:
            self._value -= 1

    def reset(self) -> None:
        self._value = 0

    def value(self) -> int:
        return self._value
