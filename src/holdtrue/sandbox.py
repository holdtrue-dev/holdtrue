"""Run a command in a bubblewrap sandbox: no network, read-only /usr and venv,
writes only to the dirs you pass.

This tool runs code an LLM just wrote, so the sandbox is the safety boundary and it
fails closed: if sandboxing is asked for but bwrap is missing (bwrap is Linux-only),
the run raises SandboxUnavailable rather than silently executing untrusted code on the
host. Running without a sandbox is only ever an explicit choice (--no-sandbox).

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


class SandboxUnavailable(RuntimeError):
    """Sandboxing was requested but bubblewrap is not installed."""


@dataclass
class RunResult:
    rc: int
    stdout: str
    stderr: str
    sandboxed: bool


def bwrap_available() -> bool:
    return BWRAP is not None


def _bwrap_args(cmd: list[str], rw_dirs: list[str], ro_dirs: list[str],
                workdir: str | None) -> list[str]:
    """Build the bwrap invocation: no network, read-only system and venv, writes
    confined to rw_dirs. Raises SandboxUnavailable if bwrap is missing."""
    if BWRAP is None:
        raise SandboxUnavailable(
            "bubblewrap (bwrap) is not installed, so this untrusted code cannot be "
            "sandboxed. Install bwrap (Linux only), or pass --no-sandbox to run it "
            "directly on your machine.")
    args = [
        BWRAP,
        "--ro-bind", "/usr", "/usr",
        "--symlink", "usr/bin", "/bin",
        "--symlink", "usr/lib", "/lib",
        "--symlink", "usr/lib64", "/lib64",
        "--ro-bind", sys.prefix, sys.prefix,
        "--ro-bind", sys.base_prefix, sys.base_prefix,
        "--tmpfs", "/tmp",
        "--setenv", "HOME", "/tmp",
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
    return args + ["--"] + cmd


def wrap(cmd: list[str], *, rw_dirs: list[str] | None = None,
         ro_dirs: list[str] | None = None, workdir: str | None = None) -> list[str]:
    """Return `cmd` wrapped in bwrap, for callers that manage their own subprocess
    (cosmic-ray). Raises SandboxUnavailable if bwrap is missing."""
    return _bwrap_args(cmd, rw_dirs or [], ro_dirs or [], workdir)


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
    if _aborted.is_set():
        return RunResult(130, "", "[holdtrue] aborted", sandbox)

    if sandbox:
        args = _bwrap_args(cmd, rw_dirs or [], ro_dirs or [], workdir)  # raises if no bwrap
        cwd = None
    else:
        args = cmd
        cwd = workdir

    rc, out, err = _collect(_spawn(args, cwd), timeout)
    return RunResult(rc, out, err, sandbox)


def popen_run(cmd: list[str], *, cwd: str | None = None,
              timeout: float = 120.0) -> tuple[int, str, str]:
    """Tracked, unsandboxed run for tools that manage their own subprocesses
    (e.g. cosmic-ray). Returns (rc, stdout, stderr)."""
    if _aborted.is_set():
        return 130, "", "[holdtrue] aborted"
    return _collect(_spawn(cmd, cwd), timeout)
