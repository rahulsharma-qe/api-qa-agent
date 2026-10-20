"""Values carried from one step to the next, and every step so far (shown when a test fails).

    context.remember("pnr", created.value("pnr"))
    api.get(f"/bookings/{context.get('pnr')}")
"""

from dataclasses import dataclass
from typing import Any, Callable, Optional

from api_test_framework.api_response import ApiResponse, describe


@dataclass
class Step:
    number: int
    response: ApiResponse


class ScenarioContext:
    def __init__(self, on_step: Optional[Callable[["Step"], None]] = None):
        self._values: dict = {}
        self.steps: list = []
        self._on_step = on_step       # e.g. attach each step to a report as it happens

    def remember(self, name: str, value: Any) -> Any:
        self._values[name] = value
        return value

    def get(self, name: str) -> Any:
        if name not in self._values:
            known = ", ".join(sorted(self._values)) or "nothing yet"
            raise KeyError(f"'{name}' was never remembered (remembered: {known})")
        return self._values[name]

    def __contains__(self, name: str) -> bool:
        return name in self._values

    @property
    def values(self) -> dict:
        return dict(self._values)

    def record(self, response: ApiResponse) -> None:
        step = Step(len(self.steps) + 1, response)
        self.steps.append(step)
        if self._on_step is not None:
            self._on_step(step)

    def history(self) -> str:
        """Every step's request and response, in order: the chain that led to a failure."""
        if not self.steps:
            return "(no requests were made)"
        return "\n".join(f"step {step.number}\n{describe(step.response)}" for step in self.steps)
