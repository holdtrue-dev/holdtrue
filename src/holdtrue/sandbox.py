"""Run a command in a sandbox: no network, read-only filesystem, writes confined.

Three sandbox tiers, in ascending isolation:

  bwrap (default) — Linux bubblewrap: no network namespace, read-only /usr and
    venv, writes only to the dirs you pass, process group killed on abort.

  docker — Docker container: same isolation goals via Docker's namespace + cgroup
    machinery. Useful in CI environments where user namespaces for bwrap are
    disabled. Requires Docker and a pre-built `holdtrue-sandbox` image
    (run `holdtrue sandbox build` to create it).

  off — unsandboxed subprocess, only with explicit --no-sandbox.

Both sandboxed tiers fail closed: if the requested sandbox is unavailable the
run raises SandboxUnavailable rather than silently executing untrusted code.

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
from pathlib import Path

BWRAP = shutil.which("bwrap")
DOCKER = shutil.which("docker")

# Docker image used when sandbox="docker".  Build it with `holdtrue sandbox build`.
DOCKER_IMAGE = "holdtrue-sandbox:latest"

_active: "set[subprocess.Popen]" = set()
_lock = threading.Lock()
_aborted = threading.Event()
_kind: str = "bwrap"  # active sandbox tier; set once at CLI startup via configure()


def configure(kind: str) -> None:
    """Set the sandbox tier for all subsequent runs: 'bwrap', 'docker', or 'off'."""
    global _kind
    _kind = kind


class SandboxUnavailable(RuntimeError):
    """Sandboxing was requested but the required tool is not installed."""


@dataclass
class RunResult:
    rc: int
    stdout: str
    stderr: str
    sandboxed: bool


def bwrap_available() -> bool:
    return BWRAP is not None


def docker_available() -> bool:
    return DOCKER is not None


def docker_image_exists() -> bool:
    """Return True if the holdtrue-sandbox Docker image is present locally."""
    if DOCKER is None:
        return False
    r = subprocess.run(
        [DOCKER, "image", "inspect", DOCKER_IMAGE],
        capture_output=True, text=True)
    return r.returncode == 0


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


def _docker_args(cmd: list[str], rw_dirs: list[str], ro_dirs: list[str],
                 workdir: str | None) -> list[str]:
    """Build a Docker invocation that mirrors the bwrap sandbox.

    The holdtrue-sandbox image provides Python plus all verification tools
    (mypy, crosshair, deal, hypothesis, pytest, cosmic-ray).  The work dirs
    are bind-mounted rw; no network is allowed.  The host venv is NOT used:
    the image's own interpreter and packages run the checks, so the command
    paths are remapped from host-venv paths to image-standard paths.

    Raises SandboxUnavailable if Docker is missing or the image is not built.
    """
    if DOCKER is None:
        raise SandboxUnavailable(
            "docker is not installed. Install Docker, or use the default bwrap sandbox.")
    if not docker_image_exists():
        raise SandboxUnavailable(
            f"Docker image {DOCKER_IMAGE!r} not found. "
            "Run `holdtrue sandbox build` to create it.")
    args = [
        DOCKER, "run", "--rm",
        "--network=none",
        "--security-opt=no-new-privileges:true",
        "--cap-drop=ALL",
        "--read-only",
        "--tmpfs=/tmp:size=512m",
        f"--user={os.getuid()}:{os.getgid()}",
    ]
    for d in ro_dirs:
        args += [f"--volume={d}:{d}:ro"]
    for d in rw_dirs:
        args += [f"--volume={d}:{d}"]
    if workdir:
        args += [f"--workdir={workdir}"]
    args += [DOCKER_IMAGE] + _remap_for_docker(cmd)
    return args


# Remap host-venv binary paths to their Docker-image equivalents.
# The image installs these tools at standard PATH locations.
def _remap_for_docker(cmd: list[str]) -> list[str]:
    from . import engine  # local import avoids a circular dependency at module load
    remap = {
        engine.PYBIN: "python3",
        engine.CROSSHAIR: "crosshair",
        engine.COSMIC_RAY: "cosmic-ray",
        engine.CR_REPORT: "cr-report",
    }
    return [remap.get(part, part) for part in cmd]


def wrap(cmd: list[str], *, rw_dirs: list[str] | None = None,
         ro_dirs: list[str] | None = None, workdir: str | None = None) -> list[str]:
    """Return `cmd` wrapped in the active sandbox tier, for callers that manage their
    own subprocess (cosmic-ray). Raises SandboxUnavailable if the sandbox is missing."""
    if _kind == "docker":
        return _docker_args(cmd, rw_dirs or [], ro_dirs or [], workdir)
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
    """Run `cmd` in the sandbox tier configured via configure().

    When sandbox=True the active tier (_kind) is used: 'bwrap' or 'docker'.
    When sandbox=False the command runs as a direct subprocess (--no-sandbox).
    """
    if _aborted.is_set():
        return RunResult(130, "", "[holdtrue] aborted", sandbox)

    if not sandbox or _kind == "off":
        args = cmd
        cwd = workdir
        sandboxed = False
    elif _kind == "docker":
        args = _docker_args(cmd, rw_dirs or [], ro_dirs or [], workdir)
        cwd = None
        sandboxed = True
    else:
        args = _bwrap_args(cmd, rw_dirs or [], ro_dirs or [], workdir)
        cwd = None
        sandboxed = True

    rc, out, err = _collect(_spawn(args, cwd), timeout)
    return RunResult(rc, out, err, sandboxed)


def popen_run(cmd: list[str], *, cwd: str | None = None,
              timeout: float = 120.0) -> tuple[int, str, str]:
    """Tracked, unsandboxed run for tools that manage their own subprocesses
    (e.g. cosmic-ray). Returns (rc, stdout, stderr)."""
    if _aborted.is_set():
        return 130, "", "[holdtrue] aborted"
    return _collect(_spawn(cmd, cwd), timeout)


def build_docker_image(*, progress: bool = True) -> int:
    """Build the holdtrue-sandbox Docker image from the bundled Dockerfile.

    Returns the docker build exit code (0 = success)."""
    if DOCKER is None:
        print("docker is not installed.")
        return 1
    dockerfile = Path(__file__).parent.parent.parent / "Dockerfile.sandbox"
    if not dockerfile.exists():
        # Try the package data path (installed wheel)
        dockerfile = Path(__file__).parent / "Dockerfile.sandbox"
    if not dockerfile.exists():
        print(f"Dockerfile.sandbox not found (looked in {dockerfile.parent}).")
        return 1
    cmd = [DOCKER, "build", "-t", DOCKER_IMAGE, "-f", str(dockerfile),
           str(dockerfile.parent)]
    if not progress:
        cmd += ["--progress=quiet"]
    p = subprocess.run(cmd)
    return p.returncode
