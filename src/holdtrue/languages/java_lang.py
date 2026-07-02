"""Java language plugin.

Toolchain: javac (compile/types), jqwik (property tests), PIT (mutation).
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


def _java_available() -> bool:
    return shutil.which("javac") is not None and shutil.which("mvn") is not None


def _run_javac(check_id: str, src: str, class_name: str) -> engine.CheckResult:
    with tempfile.TemporaryDirectory(prefix="holdtrue_java_") as tmp:
        d = Path(tmp)
        (d / f"{class_name}.java").write_text(src, encoding="utf-8")
        r = subprocess.run(["javac", f"{class_name}.java"],
                           cwd=tmp, capture_output=True, text=True, timeout=30)
        if r.returncode == 0:
            return engine.CheckResult(check_id, "types", "pass", detail="javac passed")
        return engine.CheckResult(check_id, "types", "fail",
                                  detail=(r.stdout + r.stderr)[:400])


def _run_mvn_test(check_id: str, project_dir: Path, *, label: str) -> engine.CheckResult:
    r = subprocess.run(["mvn", "-q", "test"],
                       cwd=project_dir, capture_output=True, text=True, timeout=180)
    if r.returncode == 0:
        return engine.CheckResult(check_id, label, "pass", detail="mvn test passed")
    return engine.CheckResult(check_id, label, "fail",
                              detail=(r.stdout + r.stderr)[:400])


def _run_pit(check_id: str, project_dir: Path, threshold: float) -> engine.CheckResult:
    r = subprocess.run(
        ["mvn", "-q", "org.pitest:pitest-maven:mutationCoverage",
         f"-DmutationThreshold={int(threshold * 100)}"],
        cwd=project_dir, capture_output=True, text=True, timeout=300)
    out = (r.stdout + r.stderr)
    status = "pass" if r.returncode == 0 else "fail"
    return engine.CheckResult(check_id, "mutation", status, detail=out[:200])


class JavaLanguage(Language):
    name = "java"
    display_name = "Java"
    file_extension = ".java"
    verdict_ceiling = "ENFORCED"

    def available(self) -> bool:
        return _java_available()

    def author_instructions(self) -> str:
        return """\
Write a Java contract. Set `language: java` in the manifest.
Verdict ceiling: ENFORCED (no symbolic prover for Java).

Layout (Maven project):
  contract/manifest.yaml           (language: java)
  contract/src/test/java/ContractTest.java   (jqwik property tests)
  contract_private/src/test/java/HeldoutTest.java
  contract_private/ReferenceImpl.java

The implementer writes Core.java. Tests use jqwik for property-based testing.
Use @Property and @ForAll annotations. Set `acceptance: { target_class: ENFORCED }`.
PIT mutation threshold 0.75 or higher.
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
        if not _java_available():
            results: dict[str, engine.CheckResult] = {}
            emit = make_emit(results, on_result)
            emit(na("CHK-types", "types", "javac/mvn not installed"))
            return results, classify(manifest["intent_id"], results)

        contract_dir = project / "contract"
        private_dir = project / "contract_private"
        impl_source = impl_path.read_text(encoding="utf-8")

        checks = manifest["checks"]
        threshold = checks.get("mutation", {}).get("threshold", 0.75)

        results: dict[str, engine.CheckResult] = {}
        emit = make_emit(results, on_result)

        emit(na("CHK-symbolic", "crosshair",
                "not attempted: Java has no symbolic prover. Verdict capped at ENFORCED."))

        class_name = impl_path.stem
        tasks: list[Callable[[], engine.CheckResult]] = [
            lambda: _run_javac("CHK-types", impl_source, class_name),
        ]

        shown_dir = contract_dir / "src"
        if shown_dir.exists():
            tasks.append(lambda: _run_mvn_test("CHK-prop-shown", contract_dir,
                                               label="hypothesis_shown"))

        heldout_dir = private_dir / "src"
        if heldout_dir.exists():
            tasks.append(lambda: _run_mvn_test("CHK-prop-heldout", private_dir,
                                               label="hypothesis_heldout"))

        if mutation and shown_dir.exists():
            tasks.append(lambda: _run_pit("CHK-mutation", contract_dir, threshold))

        dispatch(tasks, emit, parallel=parallel)
        return results, classify(manifest["intent_id"], results)
