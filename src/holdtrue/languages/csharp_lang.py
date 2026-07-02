"""C# language plugin.

Toolchain: dotnet (build/test), FsCheck (property tests), Stryker.NET (mutation).
No symbolic prover; verdict ceiling is ENFORCED.
"""
from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Callable

from .. import engine
from ..classify import Classification, classify
from .base import Language, dispatch, make_emit, na


def _dotnet_available() -> bool:
    return shutil.which("dotnet") is not None


def _run_dotnet_build(check_id: str, project_dir: Path) -> engine.CheckResult:
    r = subprocess.run(["dotnet", "build", "-q"],
                       cwd=project_dir, capture_output=True, text=True, timeout=120)
    if r.returncode == 0:
        return engine.CheckResult(check_id, "types", "pass", detail="dotnet build passed")
    return engine.CheckResult(check_id, "types", "fail",
                              detail=(r.stdout + r.stderr)[:400])


def _run_dotnet_test(check_id: str, project_dir: Path, *, label: str) -> engine.CheckResult:
    r = subprocess.run(["dotnet", "test", "-q"],
                       cwd=project_dir, capture_output=True, text=True, timeout=180)
    if r.returncode == 0:
        return engine.CheckResult(check_id, label, "pass", detail="dotnet test passed")
    return engine.CheckResult(check_id, label, "fail",
                              detail=(r.stdout + r.stderr)[:400])


def _run_stryker(check_id: str, project_dir: Path, threshold: float) -> engine.CheckResult:
    if not shutil.which("dotnet-stryker"):
        return na(check_id, "mutation",
                  "dotnet-stryker not installed; run `dotnet tool install -g dotnet-stryker`")
    r = subprocess.run(
        ["dotnet-stryker", "--threshold-high", str(int(threshold * 100)),
         "--threshold-low", str(int(threshold * 100)),
         "--threshold-break", str(int(threshold * 100))],
        cwd=project_dir, capture_output=True, text=True, timeout=300)
    out = (r.stdout + r.stderr)
    status = "pass" if r.returncode == 0 else "fail"
    return engine.CheckResult(check_id, "mutation", status, detail=out[:200])


class CSharpLanguage(Language):
    name = "csharp"
    display_name = "C#"
    file_extension = ".cs"
    verdict_ceiling = "ENFORCED"

    def available(self) -> bool:
        return _dotnet_available()

    def author_instructions(self) -> str:
        return """\
Write a C# contract. Set `language: csharp` in the manifest.
Verdict ceiling: ENFORCED (no symbolic prover for C#).

Layout (.NET solution):
  contract/manifest.yaml                   (language: csharp)
  contract/ContractTests/ContractTest.cs   (FsCheck property tests)
  contract_private/HeldoutTests/HeldoutTest.cs
  contract_private/ReferenceImpl.cs

The implementer writes Core.cs. Tests use FsCheck for property-based testing.
Use [Property] attribute and Prop.ForAll. Set `acceptance: { target_class: ENFORCED }`.
Stryker.NET mutation threshold 0.75 or higher.
"""

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
        if not _dotnet_available():
            results: dict[str, engine.CheckResult] = {}
            emit = make_emit(results, on_result)
            emit(na("CHK-types", "types", "dotnet not installed"))
            return results, classify(manifest["intent_id"], results)

        contract_dir = project / "contract"
        private_dir = project / "contract_private"

        checks = manifest["checks"]
        threshold = checks.get("mutation", {}).get("threshold", 0.75)

        results: dict[str, engine.CheckResult] = {}
        emit = make_emit(results, on_result)

        emit(na("CHK-symbolic", "crosshair",
                "not attempted: C# has no symbolic prover. Verdict capped at ENFORCED."))

        tasks: list[Callable[[], engine.CheckResult]] = [
            lambda: _run_dotnet_build("CHK-types", contract_dir),
        ]

        if (contract_dir / "ContractTests").exists():
            tasks.append(lambda: _run_dotnet_test("CHK-prop-shown", contract_dir,
                                                  label="hypothesis_shown"))

        if (private_dir / "HeldoutTests").exists():
            tasks.append(lambda: _run_dotnet_test("CHK-prop-heldout", private_dir,
                                                  label="hypothesis_heldout"))

        if mutation and (contract_dir / "ContractTests").exists():
            tasks.append(lambda: _run_stryker("CHK-mutation", contract_dir, threshold))

        dispatch(tasks, emit, parallel=parallel)
        return results, classify(manifest["intent_id"], results)
