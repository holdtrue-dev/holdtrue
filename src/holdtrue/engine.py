"""Run each check against an implementation and return normalized results.

Two things that are easy to get wrong:
  - CrossHair exit 0 is not a proof. The only proof signal is the verbose line
    "Exhausted calltree search with CONFIRMED". Anything else is unconfirmed.
  - Mutation with no mutable nodes reports "na", not a misleading 100%.
"""
from __future__ import annotations

import ast
import os
import re
import shutil
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from . import sandbox

VENV_BIN = Path(sys.prefix) / "bin"
CROSSHAIR = str(VENV_BIN / "crosshair")
COSMIC_RAY = str(VENV_BIN / "cosmic-ray")
CR_REPORT = str(VENV_BIN / "cr-report")
PYBIN = sys.executable

CONFIRMED_PHRASE = "Exhausted calltree search with CONFIRMED"


@dataclass
class CheckResult:
    check_id: str
    kind: str
    status: str  # pass | fail | confirmed | refuted | unconfirmed | na
    detail: str = ""
    counterexample: str | None = None
    extra: dict = field(default_factory=dict)


def _splice(decorators: list[str], impl_source: str, function: str = "clamp") -> str:
    """Inject the contract decorators onto the implementer's function via AST, then
    unparse, giving a module CrossHair can check.

    Done at the AST level because the implementer's file may start with a docstring;
    splicing decorators textually above the file would put them before the docstring,
    which is a syntax error. Dynamic wrapping does not work either: CrossHair only
    checks functions defined in the target module.
    """
    try:
        mod = ast.parse(impl_source)
        target = next((n for n in mod.body
                       if isinstance(n, ast.FunctionDef) and n.name == function), None)
        if target is None:
            target = next((n for n in mod.body if isinstance(n, ast.FunctionDef)), None)
        if target is None:
            raise ValueError("no function definition found in implementation")
        deco_nodes = [ast.parse(d[1:] if d.startswith("@") else d, mode="eval").body
                      for d in decorators]
        target.decorator_list = deco_nodes + target.decorator_list
        mod.body.insert(0, ast.parse("import deal").body[0])
        ast.fix_missing_locations(mod)
        return ast.unparse(mod)
    except Exception:
        # Fallback for a body that is already a bare, docstring-free function.
        return "import deal\n" + "\n".join(decorators) + "\n" + impl_source


def _body_to_function(signature: str, body: str) -> str:
    """Turn a negative-probe body like 'return lo' into a full typed function."""
    indented = "\n".join("    " + line for line in body.splitlines())
    return f"def {signature}:\n{indented}\n"


# --------------------------------------------------------------------------- #
# CrossHair (the proof tier)
# --------------------------------------------------------------------------- #
def run_crosshair(
    check_id: str,
    decorators: list[str],
    impl_source: str,
    *,
    function: str = "clamp",
    sandbox_on: bool = True,
    per_condition_timeout: float = 10.0,
    timeout: float = 120.0,
) -> CheckResult:
    work = tempfile.mkdtemp(prefix="holdtrue_ch_")
    try:
        chk = Path(work) / "chk.py"
        chk.write_text(_splice(decorators, impl_source, function), encoding="utf-8")
        cmd = [
            CROSSHAIR, "check", "--analysis_kind=deal",
            f"--per_condition_timeout={per_condition_timeout}", "-v", "chk.py",
        ]
        r = sandbox.run(cmd, rw_dirs=[work], workdir=work, timeout=timeout, sandbox=sandbox_on)
        combined = r.stdout + "\n" + r.stderr
        if r.rc == 1 and "error:" in r.stdout:
            cex = _parse_counterexample(r.stdout)
            return CheckResult(check_id, "crosshair", "refuted",
                               detail="CrossHair found a counterexample.",
                               counterexample=cex)
        if CONFIRMED_PHRASE in combined:
            return CheckResult(check_id, "crosshair", "confirmed",
                               detail="CrossHair exhausted all paths and confirmed "
                                      "the contract over the whole input domain.")
        # Fail closed: exit 0 without the exhaustion phrase is NOT a proof.
        reason = "aborted/timeout (no counterexample, but paths not exhausted)"
        if "Aborted calltree search" in combined:
            reason = "search aborted before exhausting paths (timeout/iteration limit)"
        return CheckResult(check_id, "crosshair", "unconfirmed",
                           detail=f"No proof: {reason}.")
    finally:
        shutil.rmtree(work, ignore_errors=True)


def _parse_counterexample(stdout: str) -> str | None:
    for line in stdout.splitlines():
        m = re.search(r"error:\s*(.*)", line)
        if m:
            return m.group(1).strip()
    return None


# --------------------------------------------------------------------------- #
# Types (the gate)
# --------------------------------------------------------------------------- #
def run_types(check_id: str, impl_source: str, *, sandbox_on: bool = True,
              timeout: float = 60.0) -> CheckResult:
    work = tempfile.mkdtemp(prefix="holdtrue_ty_")
    try:
        (Path(work) / "core.py").write_text(impl_source, encoding="utf-8")
        cmd = [PYBIN, "-m", "mypy", "--strict", "--no-error-summary", "core.py"]
        r = sandbox.run(cmd, rw_dirs=[work], workdir=work, timeout=timeout, sandbox=sandbox_on)
        if r.rc == 0:
            return CheckResult(check_id, "types", "pass", detail="mypy --strict clean.")
        return CheckResult(check_id, "types", "fail",
                           detail=r.stdout.strip() or r.stderr.strip())
    finally:
        shutil.rmtree(work, ignore_errors=True)


# --------------------------------------------------------------------------- #
# Property tests (sampling): shown and held-out
# --------------------------------------------------------------------------- #
def run_pytest(check_id: str, kind_label: str, test_source: str, impl_source: str,
               *, deps: dict[str, str] | None = None, sandbox_on: bool = True,
               timeout: float = 120.0) -> CheckResult:
    work = tempfile.mkdtemp(prefix="holdtrue_pt_")
    try:
        (Path(work) / "core.py").write_text(impl_source, encoding="utf-8")
        (Path(work) / "test_check.py").write_text(test_source, encoding="utf-8")
        for name, src in (deps or {}).items():
            (Path(work) / name).write_text(src, encoding="utf-8")
        cmd = [PYBIN, "-m", "pytest", "-q", "-p", "no:cacheprovider", "test_check.py"]
        r = sandbox.run(cmd, rw_dirs=[work], workdir=work, timeout=timeout, sandbox=sandbox_on)
        if r.rc == 0:
            return CheckResult(check_id, kind_label, "pass",
                               detail="property holds over sampled inputs (not a proof).")
        return CheckResult(check_id, kind_label, "fail",
                           detail=_tail(r.stdout, 12),
                           counterexample=_parse_hypothesis_falsifying(r.stdout))
    finally:
        shutil.rmtree(work, ignore_errors=True)


def _parse_hypothesis_falsifying(stdout: str) -> str | None:
    for line in stdout.splitlines():
        if "Falsifying example" in line:
            return line.strip()
    return None


# --------------------------------------------------------------------------- #
# Negative-behavior probe (mandatory pre-GUARANTEED)
# --------------------------------------------------------------------------- #
def run_negative_probe(check_id: str, signature: str, decorators: list[str],
                       must_reject: list[str], *, function: str = "clamp",
                       sandbox_on: bool = True) -> CheckResult:
    survivors = []
    for body in must_reject:
        fn = _body_to_function(signature, body)
        r = run_crosshair(f"{check_id}:{body}", decorators, fn, function=function,
                          sandbox_on=sandbox_on)
        # The contract must REJECT (refute) each broken body. If CrossHair confirms
        # or cannot refute, the contract is too weak for this body.
        if r.status != "refuted":
            survivors.append({"body": body, "crosshair_status": r.status})
    if survivors:
        return CheckResult(check_id, "negative_probe", "fail",
                           detail=f"contract failed to reject {len(survivors)} broken "
                                  f"implementation(s)",
                           extra={"survivors": survivors})
    return CheckResult(check_id, "negative_probe", "pass",
                       detail=f"contract rejects all {len(must_reject)} broken bodies.")


# --------------------------------------------------------------------------- #
# Mutation testing: mutates the implementation
# --------------------------------------------------------------------------- #
def run_mutation(check_id: str, impl_source: str, test_files: dict[str, str],
                 threshold: float, *, timeout: float = 300.0) -> CheckResult:
    work = tempfile.mkdtemp(prefix="holdtrue_mut_")
    try:
        wp = Path(work)
        (wp / "core.py").write_text(impl_source, encoding="utf-8")
        test_targets = []
        for name, src in test_files.items():
            (wp / name).write_text(src, encoding="utf-8")
            if name.startswith("test_"):
                test_targets.append(name)
        test_cmd = f"{PYBIN} -m pytest -x -q -p no:cacheprovider " + " ".join(test_targets)
        (wp / "cr.toml").write_text(
            "[cosmic-ray]\n"
            'module-path = "core.py"\n'
            "timeout = 30.0\n"
            f'test-command = "{test_cmd}"\n'
            "[cosmic-ray.distributor]\n"
            'name = "local"\n',
            encoding="utf-8",
        )
        # cosmic-ray spawns its own test subprocesses; run it directly (not in bwrap).
        env = dict(os.environ)
        env.pop("VIRTUAL_ENV", None)
        import subprocess
        init = subprocess.run([COSMIC_RAY, "init", "cr.toml", "cr.sqlite"],
                              cwd=work, capture_output=True, text=True, timeout=60)
        if init.returncode != 0:
            return CheckResult(check_id, "mutation", "na",
                               detail=f"cosmic-ray init failed: {init.stderr[:200]}")
        ex = subprocess.run([COSMIC_RAY, "exec", "cr.toml", "cr.sqlite"],
                            cwd=work, capture_output=True, text=True, timeout=timeout)
        rep = subprocess.run([CR_REPORT, "cr.sqlite"], cwd=work,
                             capture_output=True, text=True, timeout=60)
        total, surviving = _parse_cr_report(rep.stdout)
        if total == 0:
            return CheckResult(check_id, "mutation", "na",
                               detail="no mutable nodes in the implementation, so "
                                      "mutation score is not applicable.",
                               extra={"total": 0})
        killed = total - surviving
        score = killed / total
        status = "pass" if score >= threshold else "fail"
        return CheckResult(check_id, "mutation", status,
                           detail=f"mutation score {score:.3f} "
                                  f"({killed}/{total} killed, {surviving} survived; "
                                  f"threshold {threshold}).",
                           extra={"total": total, "killed": killed,
                                  "surviving": surviving, "score": round(score, 4),
                                  "threshold": threshold})
    finally:
        shutil.rmtree(work, ignore_errors=True)


def _parse_cr_report(out: str) -> tuple[int, int]:
    total = surviving = 0
    for line in out.splitlines():
        m = re.search(r"total jobs:\s*(\d+)", line)
        if m:
            total = int(m.group(1))
        m = re.search(r"surviving mutants:\s*(\d+)", line)
        if m:
            surviving = int(m.group(1))
    return total, surviving


def _tail(s: str, n: int) -> str:
    return "\n".join(s.splitlines()[-n:])
