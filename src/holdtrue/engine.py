"""Run each check against an implementation and return normalized results.

Two things that are easy to get wrong:
  - CrossHair exit 0 is not a proof. The only proof signal is the verbose line
    "Exhausted calltree search with CONFIRMED". Anything else is unconfirmed.
  - Mutation with no mutable nodes reports "na", not a misleading 100%.
"""
from __future__ import annotations

import ast
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
        _insert_import_deal(mod)
        ast.fix_missing_locations(mod)
        return ast.unparse(mod)
    except Exception:
        # Fallback for a body that is already a bare, docstring-free function.
        return "import deal\n" + "\n".join(decorators) + "\n" + impl_source


def _insert_import_deal(mod: ast.Module) -> None:
    """Insert `import deal` after any module docstring and any `from __future__`
    imports, both of which must stay first. Inserting at position 0 would push them
    down and raise SyntaxError (`from __future__ imports must occur at the beginning`),
    which silently breaks both the CrossHair proof and the runtime negative-probe."""
    idx = 0
    if (mod.body and isinstance(mod.body[0], ast.Expr)
            and isinstance(mod.body[0].value, ast.Constant)
            and isinstance(mod.body[0].value.value, str)):
        idx = 1
    while (idx < len(mod.body) and isinstance(mod.body[idx], ast.ImportFrom)
           and mod.body[idx].module == "__future__"):
        idx += 1
    mod.body.insert(idx, ast.parse("import deal").body[0])


def _body_to_function(signature: str, body: str) -> str:
    """Turn a negative-probe body like 'return lo' into a full typed function."""
    indented = "\n".join("    " + line for line in body.splitlines())
    return f"def {signature}:\n{indented}\n"


def _probe_module(base_src: str, decorators: list[str], signature: str, body: str,
                  function: str) -> str:
    """Build a module that is `base_src` with `function` replaced by a one-line broken
    body and the contract decorators spliced onto it.

    The correct siblings from base_src stay, so a shared property test that imports and
    calls every function in a multi-function contract still resolves. Only the broken
    function is decorated, so only its contract fires; if its body actually satisfies
    the contract, nothing raises and the probe correctly records a survivor.
    """
    mod = ast.parse(base_src)
    mod.body = [n for n in mod.body
                if not (isinstance(n, ast.FunctionDef) and n.name == function)]
    broken = ast.parse(_body_to_function(signature, body)).body[0]
    deco_nodes = [ast.parse(d[1:] if d.startswith("@") else d, mode="eval").body
                  for d in decorators]
    broken.decorator_list = deco_nodes  # type: ignore[attr-defined]
    _insert_import_deal(mod)
    mod.body.append(broken)
    ast.fix_missing_locations(mod)
    return ast.unparse(mod)


# --------------------------------------------------------------------------- #
# CrossHair (the proof tier)
# --------------------------------------------------------------------------- #
def run_crosshair(
    check_id: str,
    decorators: list[str],
    impl_source: str,
    *,
    function: str = "clamp",
    extra: dict[str, str] | None = None,
    sandbox_on: bool = True,
    per_condition_timeout: float = 10.0,
    timeout: float = 120.0,
) -> CheckResult:
    work = tempfile.mkdtemp(prefix="holdtrue_ch_")
    try:
        chk = Path(work) / "chk.py"
        chk.write_text(_splice(decorators, impl_source, function), encoding="utf-8")
        for name, src in (extra or {}).items():
            (Path(work) / name).write_text(src, encoding="utf-8")
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
def run_types(check_id: str, impl_source: str, *, extra: dict[str, str] | None = None,
              sandbox_on: bool = True, timeout: float = 60.0) -> CheckResult:
    work = tempfile.mkdtemp(prefix="holdtrue_ty_")
    try:
        (Path(work) / "core.py").write_text(impl_source, encoding="utf-8")
        for name, src in (extra or {}).items():
            (Path(work) / name).write_text(src, encoding="utf-8")
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


def run_negative_probe_runtime(check_id: str, signature: str, decorators: list[str],
                               must_reject: list[str], shown_src: str, *,
                               function: str = "clamp", prelude: str = "",
                               base_src: str | None = None,
                               deps: dict[str, str] | None = None,
                               sandbox_on: bool = True) -> CheckResult:
    """The runtime counterpart of the negative-probe, for contracts CrossHair cannot
    reason over (pydantic models, rich types). Each broken body is spliced with the
    contract and run against the shown property: a strong contract makes the property
    FAIL (the deal postcondition raises, or the result disagrees). A body that passes
    the property survived, so the contract is too weak over the sample.

    In a multi-function contract the shared property test imports and calls every
    function, so `base_src` (the reference module) supplies the correct siblings and
    only `function` is replaced by the broken body. Without it, the broken body stands
    alone (the single-function case)."""
    survivors = []
    for body in must_reject:
        if base_src is not None:
            core = _probe_module(base_src, decorators, signature, body, function)
        else:
            impl = prelude + _body_to_function(signature, body)
            core = _splice(decorators, impl, function)
        r = run_pytest(f"{check_id}:{body}", "probe", shown_src, core, deps=deps,
                       sandbox_on=sandbox_on)
        if r.status != "fail":  # the property did not reject this broken body
            survivors.append({"body": body, "result": r.status})
    if survivors:
        return CheckResult(check_id, "negative_probe", "fail",
                           detail=f"contract failed to reject {len(survivors)} broken "
                                  f"implementation(s) at runtime",
                           extra={"survivors": survivors})
    return CheckResult(check_id, "negative_probe", "pass",
                       detail=f"contract rejects all {len(must_reject)} broken bodies "
                              "at runtime.")


# --------------------------------------------------------------------------- #
# Mutation testing: mutates the implementation
# --------------------------------------------------------------------------- #
def run_mutation(check_id: str, impl_source: str, test_files: dict[str, str],
                 threshold: float, *, sandbox_on: bool = True,
                 timeout: float = 300.0) -> CheckResult:
    # cosmic-ray imports the module (init) and runs mutated copies of it (exec), so
    # both touch LLM-written code and must be sandboxed. Fail closed rather than run
    # mutants on the host when sandboxing was asked for but is unavailable.
    if sandbox_on and not sandbox.bwrap_available():
        return CheckResult(check_id, "mutation", "na",
                           detail="skipped: sandboxing requested but bubblewrap is "
                                  "missing, and mutation runs untrusted code.")
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
        # cosmic-ray spawns its own pytest subprocesses, so run it tracked (via
        # popen_run) rather than through sandbox.run, so the whole group stays
        # killable. When sandboxing, wrap the two steps that touch untrusted code
        # (init imports the module, exec runs the mutants) in bwrap; cr-report only
        # reads the results db, so it needs no sandbox.
        def maybe_box(cmd: list[str]) -> list[str]:
            return sandbox.wrap(cmd, rw_dirs=[work], workdir=work) if sandbox_on else cmd

        rc_init, _, err_init = sandbox.popen_run(
            maybe_box([COSMIC_RAY, "init", "cr.toml", "cr.sqlite"]), cwd=work, timeout=60)
        if rc_init != 0:
            return CheckResult(check_id, "mutation", "na",
                               detail=f"cosmic-ray init failed: {err_init[:200]}")
        sandbox.popen_run(maybe_box([COSMIC_RAY, "exec", "cr.toml", "cr.sqlite"]),
                          cwd=work, timeout=timeout)
        _, rep_out, _ = sandbox.popen_run([CR_REPORT, "cr.sqlite"], cwd=work, timeout=60)
        total, surviving = _parse_cr_report(rep_out)
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


def run_oracle_mutation(check_id: str, oracle_source: str, shown_src: str,
                         heldout_src: str, threshold: float, *,
                         sandbox_on: bool = True,
                         timeout: float = 300.0) -> CheckResult:
    """Mutate the reference oracle and check whether the test suite catches it.

    Uses the same mutation infrastructure as run_mutation but with the oracle as
    the target module. The held-out differential test compares the mutated oracle
    against the unmodified oracle (both copies supplied): a mutation that changes
    the oracle's behaviour will be caught by the differential comparison, giving
    an honest measure of how much the test suite distinguishes correct from broken
    oracle implementations."""
    return run_mutation(
        check_id, oracle_source,
        {"test_shown.py": shown_src, "test_heldout.py": heldout_src,
         "reference_impl.py": oracle_source},
        threshold, sandbox_on=sandbox_on, timeout=timeout)


def _tail(s: str, n: int) -> str:
    return "\n".join(s.splitlines()[-n:])
