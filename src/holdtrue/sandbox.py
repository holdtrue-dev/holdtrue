"""Run a command in a bubblewrap sandbox: no network, read-only /usr and venv,
writes only to the dirs you pass. Falls back to a plain subprocess if bwrap is
missing.

uv venvs symlink the interpreter into sys.base_prefix, so that path is bound too
or the interpreter is a dangling symlink inside the sandbox.

Every run is tracked in a registry and launched in its own process group, so a
caller (the TUI on quit, or Ctrl-C on the CLI) can abort in-flight work and kill
the whole group, including grandchildren like cosmic-ray's pytest workers.
"""
from __future__ import annotations

import os
import shutil
import signal
import subprocess
import sys
import threading
from dataclasses import dataclass

BWRAP = shutil.which("bwrap")

_active: "set[subprocess.Popen]" = set()
_lock = threading.Lock()
_aborted = threading.Event()


@dataclass
class RunResult:
    rc: int
    stdout: str
    stderr: str
    sandboxed: bool


def bwrap_available() -> bool:
    return BWRAP is not None


def abort_all() -> None:
    """Refuse further runs and kill every in-flight process group."""
    _aborted.set()
    with _lock:
        procs = list(_active)
    for p in procs:
        try:
            os.killpg(os.getpgid(p.pid), signal.SIGKILL)
        except Exception:
            try:
                p.kill()
            except Exception:
                pass


def track(p: "subprocess.Popen") -> None:
    """Register an externally-created process group so abort_all() can kill it.
    Used for the LLM agent subprocess, which runs unsandboxed but should still die
    when the TUI quits."""
    with _lock:
        _active.add(p)


def untrack(p: "subprocess.Popen") -> None:
    with _lock:
        _active.discard(p)


def aborted() -> bool:
    return _aborted.is_set()


def _spawn(args: list[str], cwd: str | None) -> subprocess.Popen:
    p = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                         text=True, cwd=cwd, start_new_session=True)
    with _lock:
        _active.add(p)
    return p


def _collect(p: subprocess.Popen, timeout: float) -> tuple[int, str, str]:
    try:
        out, err = p.communicate(timeout=timeout)
        rc = p.returncode
    except subprocess.TimeoutExpired:
        try:
            os.killpg(os.getpgid(p.pid), signal.SIGKILL)
        except Exception:
            p.kill()
        out, err = p.communicate()
        rc, err = 124, (err or "") + "\n[holdtrue] TIMEOUT"
    finally:
        with _lock:
            _active.discard(p)
    return rc, out or "", err or ""


def run(cmd: list[str], *, rw_dirs: list[str] | None = None,
        ro_dirs: list[str] | None = None, workdir: str | None = None,
        timeout: float = 120.0, sandbox: bool = True) -> RunResult:
    rw_dirs = rw_dirs or []
    ro_dirs = ro_dirs or []
    use_sandbox = sandbox and BWRAP is not None
    if _aborted.is_set():
        return RunResult(130, "", "[holdtrue] aborted", use_sandbox)

    if use_sandbox:
        venv = sys.prefix
        base = sys.base_prefix
        args = [
            BWRAP,
            "--ro-bind", "/usr", "/usr",
            "--symlink", "usr/bin", "/bin",
            "--symlink", "usr/lib", "/lib",
            "--symlink", "usr/lib64", "/lib64",
            "--ro-bind", venv, venv,
            "--ro-bind", base, base,
            "--tmpfs", "/tmp",
            "--proc", "/proc",
            "--dev", "/dev",
            "--unshare-all",
            "--die-with-parent",
            "--new-session",
        ]
        for d in ro_dirs:
            args += ["--ro-bind", d, d]
        for d in rw_dirs:
            args += ["--bind", d, d]
        if workdir:
            args += ["--chdir", workdir]
        args += ["--"] + cmd
        cwd = None
    else:
        args = cmd
        cwd = workdir

    rc, out, err = _collect(_spawn(args, cwd), timeout)
    return RunResult(rc, out, err, use_sandbox)


def popen_run(cmd: list[str], *, cwd: str | None = None,
              timeout: float = 120.0) -> tuple[int, str, str]:
    """Tracked, unsandboxed run for tools that manage their own subprocesses
    (e.g. cosmic-ray). Returns (rc, stdout, stderr)."""
    if _aborted.is_set():
        return 130, "", "[holdtrue] aborted"
    return _collect(_spawn(cmd, cwd), timeout)
