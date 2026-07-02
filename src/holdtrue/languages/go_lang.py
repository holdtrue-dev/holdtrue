"""Go language plugin.

Toolchain: go vet (types/static), rapid (property tests), gremlins (mutation).
No symbolic prover exists for Go; verdict ceiling is ENFORCED.
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


def _go_available() -> bool:
    return shutil.which("go") is not None


def _run_go_vet(check_id: str, src: str) -> engine.CheckResult:
    with tempfile.TemporaryDirectory(prefix="holdtrue_go_") as tmp:
        d = Path(tmp)
        (d / "go.mod").write_text("module contract\n\ngo 1.21\n", encoding="utf-8")
        (d / "core.go").write_text(src, encoding="utf-8")
        r = subprocess.run(["go", "vet", "./..."],
                           cwd=tmp, capture_output=True, text=True, timeout=60)
        if r.returncode == 0:
            return engine.CheckResult(check_id, "types", "pass", detail="go vet passed")
        return engine.CheckResult(check_id, "types", "fail",
                                  detail=(r.stdout + r.stderr)[:400])


def _run_go_test(check_id: str, src: str, test_src: str,
                 ref_src: str | None, *, label: str) -> engine.CheckResult:
    with tempfile.TemporaryDirectory(prefix="holdtrue_go_") as tmp:
        d = Path(tmp)
        (d / "go.mod").write_text(
            "module contract\n\ngo 1.21\n\nrequire pgregory.net/rapid v1.1.0\n",
            encoding="utf-8")
        (d / "go.sum").write_text("", encoding="utf-8")
        (d / "core.go").write_text(src, encoding="utf-8")
        if ref_src:
            (d / "reference.go").write_text(ref_src, encoding="utf-8")
        (d / "core_test.go").write_text(test_src, encoding="utf-8")
        r = subprocess.run(
            ["go", "test", "-v", "./..."],
            cwd=tmp, capture_output=True, text=True, timeout=120,
            env={**__import__("os").environ, "GOFLAGS": "-mod=mod"})
        if r.returncode == 0:
            return engine.CheckResult(check_id, label, "pass", detail="go test passed")
        return engine.CheckResult(check_id, label, "fail",
                                  detail=(r.stdout + r.stderr)[:400])


def _run_gremlins(check_id: str, src: str, test_src: str,
                  threshold: float) -> engine.CheckResult:
    if not shutil.which("gremlins"):
        return na(check_id, "mutation", "gremlins not installed; mutation skipped")
    with tempfile.TemporaryDirectory(prefix="holdtrue_grem_") as tmp:
        d = Path(tmp)
        (d / "go.mod").write_text(
            "module contract\n\ngo 1.21\n\nrequire pgregory.net/rapid v1.1.0\n",
            encoding="utf-8")
        (d / "go.sum").write_text("", encoding="utf-8")
        (d / "core.go").write_text(src, encoding="utf-8")
        (d / "core_test.go").write_text(test_src, encoding="utf-8")
        r = subprocess.run(
            ["gremlins", "unleash", "--threshold", str(int(threshold * 100))],
            cwd=tmp, capture_output=True, text=True, timeout=300,
            env={**__import__("os").environ, "GOFLAGS": "-mod=mod"})
        out = (r.stdout + r.stderr)
        status = "pass" if r.returncode == 0 else "fail"
        return engine.CheckResult(check_id, "mutation", status, detail=out[:200])


class GoLanguage(Language):
    name = "go"
    display_name = "Go"
    file_extension = ".go"
    verdict_ceiling = "ENFORCED"

    def available(self) -> bool:
        return _go_available()

    def author_instructions(self) -> str:
        return """\
Write a Go contract. Set `language: go` in the manifest.
Verdict ceiling: ENFORCED (no symbolic prover for Go).

Layout:
  contract/manifest.yaml         (language: go)
  contract/tests_shown/core_test.go    (rapid property tests, package contract)
  contract_private/tests_heldout/core_heldout_test.go
  contract_private/reference_impl.go  (package contract, function Reference<Name>)

The implementer writes core.go (package contract). Tests use pgregory.net/rapid for
property-based testing. Set `acceptance: { target_class: ENFORCED }`.
Use gremlins threshold 0.75 or higher.
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
        if not _go_available():
            results: dict[str, engine.CheckResult] = {}
            emit = make_emit(results, on_result)
            emit(na("CHK-types", "types", "go not installed"))
            return results, classify(manifest["intent_id"], results)

        contract_dir = project / "contract"
        private_dir = project / "contract_private"
        impl_source = impl_path.read_text(encoding="utf-8")

        checks = manifest["checks"]
        shown_src = (contract_dir / checks["hypothesis_shown"]).read_text(encoding="utf-8")
        heldout_src = (private_dir / checks["hypothesis_heldout"]).read_text(encoding="utf-8")
        ref_src = (private_dir / "reference_impl.go").read_text(encoding="utf-8")
        threshold = checks.get("mutation", {}).get("threshold", 0.75)

        results: dict[str, engine.CheckResult] = {}
        emit = make_emit(results, on_result)

        emit(na("CHK-symbolic", "crosshair",
                "not attempted: Go has no symbolic prover. Verdict capped at ENFORCED."))

        tasks: list[Callable[[], engine.CheckResult]] = [
            lambda: _run_go_vet("CHK-types", impl_source),
            lambda: _run_go_test("CHK-prop-shown", impl_source, shown_src, None,
                                 label="hypothesis_shown"),
            lambda: _run_go_test("CHK-prop-heldout", impl_source, heldout_src, ref_src,
                                 label="hypothesis_heldout"),
        ]

        if mutation:
            tasks.append(lambda: _run_gremlins("CHK-mutation", impl_source,
                                               shown_src + "\n" + heldout_src, threshold))

        dispatch(tasks, emit, parallel=parallel)
        return results, classify(manifest["intent_id"], results)
