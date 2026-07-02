"""Rust language plugin.

Toolchain: cargo (build/test), proptest (property tests), cargo-mutants (mutation).
Kani is the symbolic prover — when available, it can reach GUARANTEED.
Without Kani, the verdict ceiling is ENFORCED.
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


def _cargo_available() -> bool:
    return shutil.which("cargo") is not None


def _kani_available() -> bool:
    return shutil.which("cargo-kani") is not None


def _run_cargo_test(check_id: str, src: str, test_src: str, *, label: str) -> engine.CheckResult:
    with tempfile.TemporaryDirectory(prefix="holdtrue_rust_") as tmp:
        d = Path(tmp)
        (d / "Cargo.toml").write_text(
            '[package]\nname = "contract"\nversion = "0.1.0"\nedition = "2021"\n'
            '\n[dependencies]\nproptest = "1"\n', encoding="utf-8")
        src_dir = d / "src"
        src_dir.mkdir()
        (src_dir / "lib.rs").write_text(src + "\n\n" + test_src, encoding="utf-8")
        r = subprocess.run(
            ["cargo", "test", "--quiet"],
            cwd=tmp, capture_output=True, text=True, timeout=120)
        if r.returncode == 0:
            return engine.CheckResult(check_id, label, "pass",
                                      detail="cargo test passed")
        return engine.CheckResult(check_id, label, "fail",
                                  detail=(r.stdout + r.stderr)[:400])


def _run_kani(check_id: str, src: str, harness: str) -> engine.CheckResult:
    if not _kani_available():
        return na(check_id, "crosshair", "kani not installed; GUARANTEED not reachable")
    with tempfile.TemporaryDirectory(prefix="holdtrue_kani_") as tmp:
        d = Path(tmp)
        (d / "Cargo.toml").write_text(
            '[package]\nname = "contract"\nversion = "0.1.0"\nedition = "2021"\n',
            encoding="utf-8")
        src_dir = d / "src"
        src_dir.mkdir()
        (src_dir / "lib.rs").write_text(src + "\n\n" + harness, encoding="utf-8")
        r = subprocess.run(
            ["cargo", "kani", "--quiet"],
            cwd=tmp, capture_output=True, text=True, timeout=300)
        if r.returncode == 0:
            return engine.CheckResult(check_id, "crosshair", "confirmed",
                                      detail="Kani exhausted the domain: proven for all inputs")
        out = (r.stdout + r.stderr)[:400]
        if "VERIFICATION FAILED" in out or "counterexample" in out.lower():
            return engine.CheckResult(check_id, "crosshair", "refuted",
                                      detail="Kani found a counterexample", counterexample=out)
        return engine.CheckResult(check_id, "crosshair", "unconfirmed",
                                  detail=f"Kani did not confirm: {out[:200]}")


def _run_cargo_mutants(check_id: str, src: str, test_src: str,
                       threshold: float) -> engine.CheckResult:
    if not shutil.which("cargo-mutants"):
        return na(check_id, "mutation", "cargo-mutants not installed; mutation skipped")
    with tempfile.TemporaryDirectory(prefix="holdtrue_mutants_") as tmp:
        d = Path(tmp)
        (d / "Cargo.toml").write_text(
            '[package]\nname = "contract"\nversion = "0.1.0"\nedition = "2021"\n'
            '\n[dependencies]\nproptest = "1"\n', encoding="utf-8")
        src_dir = d / "src"
        src_dir.mkdir()
        (src_dir / "lib.rs").write_text(src + "\n\n" + test_src, encoding="utf-8")
        r = subprocess.run(
            ["cargo", "mutants", "--quiet", "--output", str(d / "mutants_out")],
            cwd=tmp, capture_output=True, text=True, timeout=300)
        summary = (d / "mutants_out" / "caught.txt")
        missed = (d / "mutants_out" / "missed.txt")
        caught = len(summary.read_text().splitlines()) if summary.exists() else 0
        miss = len(missed.read_text().splitlines()) if missed.exists() else 0
        total = caught + miss
        score = caught / total if total > 0 else 1.0
        status = "pass" if score >= threshold else "fail"
        return engine.CheckResult(check_id, "mutation", status,
                                  detail=f"score {score:.0%} ({caught}/{total} caught)")


class RustLanguage(Language):
    name = "rust"
    display_name = "Rust"
    file_extension = ".rs"
    verdict_ceiling = "GUARANTEED"  # when Kani is available

    def available(self) -> bool:
        return _cargo_available()

    def author_instructions(self) -> str:
        ceiling = "GUARANTEED (Kani installed)" if _kani_available() else "ENFORCED (Kani not installed)"
        return f"""\
Write a Rust contract. Set `language: rust` in the manifest.
Verdict ceiling: {ceiling}.

Layout:
  contract/manifest.yaml         (language: rust)
  contract/tests_shown/test_<name>.rs   (proptest property tests)
  contract_private/tests_heldout/test_<name>_heldout.rs
  contract_private/reference_impl.rs

The implementer writes core.rs. Tests use proptest for property-based testing.
{"Include a `checks.kani.harness` key with a #[kani::proof] harness for symbolic verification." if _kani_available() else "Kani is not installed; aim for ENFORCED."}
Use cargo-mutants threshold 0.80 or higher.
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
        if not _cargo_available():
            results: dict[str, engine.CheckResult] = {}
            emit = make_emit(results, on_result)
            emit(na("CHK-types", "types", "cargo not installed"))
            return results, classify(manifest["intent_id"], results)

        contract_dir = project / "contract"
        private_dir = project / "contract_private"
        impl_source = impl_path.read_text(encoding="utf-8")

        checks = manifest["checks"]
        shown_src = (contract_dir / checks["hypothesis_shown"]).read_text(encoding="utf-8")
        heldout_src = (private_dir / checks["hypothesis_heldout"]).read_text(encoding="utf-8")
        ref_src = (private_dir / "reference_impl.rs").read_text(encoding="utf-8")
        threshold = checks.get("mutation", {}).get("threshold", 0.80)
        kani_harness = checks.get("kani", {}).get("harness", "")

        results: dict[str, engine.CheckResult] = {}
        emit = make_emit(results, on_result)

        tasks: list[Callable[[], engine.CheckResult]] = [
            lambda: _run_cargo_test("CHK-prop-shown", impl_source, shown_src,
                                    label="hypothesis_shown"),
            lambda: _run_cargo_test("CHK-prop-heldout", impl_source + "\n" + ref_src,
                                    heldout_src, label="hypothesis_heldout"),
        ]

        if kani_harness:
            tasks.append(lambda: _run_kani("CHK-symbolic", impl_source, kani_harness))
        else:
            emit(na("CHK-symbolic", "crosshair",
                    "no Kani harness in manifest; GUARANTEED not reachable"))

        if mutation:
            tasks.append(lambda: _run_cargo_mutants("CHK-mutation", impl_source,
                                                    shown_src + "\n" + heldout_src,
                                                    threshold))

        emit(na("CHK-types", "types", "Rust type-checking is performed by cargo test"))
        dispatch(tasks, emit, parallel=parallel)
        return results, classify(manifest["intent_id"], results)
