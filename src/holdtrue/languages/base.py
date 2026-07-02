"""Language plugin base class and shared utilities."""
from __future__ import annotations

import concurrent.futures
import threading
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Callable

from .. import engine
from ..classify import Classification


class Language(ABC):
    """A holdtrue language plugin.

    Each language provides toolchain availability, an author-prompt fragment,
    and a check runner that produces a results dict and Classification.
    Subclasses set class-level attributes and implement the three abstract methods.
    """

    name: str            # manifest key: "python", "typescript", "rust", ...
    display_name: str    # human label: "Python", "TypeScript", ...
    file_extension: str  # ".py", ".ts", ".rs", ...
    verdict_ceiling: str # "GUARANTEED" or "ENFORCED"

    @abstractmethod
    def available(self) -> bool:
        """Return True if the required toolchain is installed."""

    @abstractmethod
    def author_instructions(self) -> str:
        """Return the language-specific fragment appended to the author prompt."""

    @abstractmethod
    def run_checks(
        self,
        project: Path,
        impl_path: Path,
        manifest: dict,
        *,
        sandbox_on: bool,
        mutation: bool,
        oracle_mutation: bool,
        parallel: bool,
        on_result: Callable[[engine.CheckResult], None] | None,
    ) -> tuple[dict[str, engine.CheckResult], Classification]:
        """Run all checks and return (results, classification)."""


def na(check_id: str, kind: str, reason: str) -> engine.CheckResult:
    """Return a not-available CheckResult for a missing or unsupported tool."""
    return engine.CheckResult(check_id, kind, "na", detail=reason)


def make_emit(
    results: dict[str, engine.CheckResult],
    on_result: Callable[[engine.CheckResult], None] | None,
) -> Callable[[engine.CheckResult], None]:
    """Return a thread-safe emit function that writes into results and calls on_result."""
    _lock = threading.Lock()

    def emit(r: engine.CheckResult) -> None:
        with _lock:
            results[r.kind] = r
            if on_result:
                on_result(r)

    return emit


def dispatch(
    tasks: list[Callable[[], engine.CheckResult]],
    emit: Callable[[engine.CheckResult], None],
    *,
    parallel: bool,
) -> None:
    """Run tasks and emit each result, in parallel or sequentially."""
    if parallel and len(tasks) > 1:
        with concurrent.futures.ThreadPoolExecutor() as ex:
            futs = [ex.submit(t) for t in tasks]
            for fut in concurrent.futures.as_completed(futs):
                emit(fut.result())
    else:
        for t in tasks:
            emit(t())
