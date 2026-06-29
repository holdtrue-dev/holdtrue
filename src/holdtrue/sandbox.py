"""Run a command in a bubblewrap sandbox: no network, read-only /usr and venv,
writes only to the dirs you pass. Falls back to a plain subprocess if bwrap is
missing.

uv venvs symlink the interpreter into sys.base_prefix, so that path is bound too
or the interpreter is a dangling symlink inside the sandbox.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from dataclasses import dataclass

BWRAP = shutil.which("bwrap")


@dataclass
class RunResult:
    rc: int
    stdout: str
    stderr: str
    sandboxed: bool


def bwrap_available() -> bool:
    return BWRAP is not None


def run(
    cmd: list[str],
    *,
    rw_dirs: list[str] | None = None,
    ro_dirs: list[str] | None = None,
    workdir: str | None = None,
    timeout: float = 120.0,
    sandbox: bool = True,
) -> RunResult:
    """Run ``cmd``. With sandbox=True and bwrap present, run inside the verified
    bwrap profile: read-only /usr + venv + base interpreter, a fresh tmpfs /tmp,
    no network (``--unshare-all``), and only ``rw_dirs`` writable."""
    rw_dirs = rw_dirs or []
    ro_dirs = ro_dirs or []
    use_sandbox = sandbox and BWRAP is not None

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
        popen_cwd = None
    else:
        args = cmd
        popen_cwd = workdir

    try:
        p = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=popen_cwd,
        )
        return RunResult(p.returncode, p.stdout, p.stderr, use_sandbox)
    except subprocess.TimeoutExpired as e:
        out = e.stdout or ""
        err = (e.stderr or "") + f"\n[holdtrue] TIMEOUT after {timeout}s"
        if isinstance(out, bytes):
            out = out.decode(errors="replace")
        if isinstance(err, bytes):
            err = err.decode(errors="replace")
        return RunResult(124, out, err, use_sandbox)
