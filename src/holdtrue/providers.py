"""Pluggable LLM providers: who actually writes the contract and the code.

holdtrue calls an LLM in exactly two places, the author and the implementer. A
Provider is the seam between holdtrue and whatever writes the files. There are two
shapes:

  agent : a headless coding-agent CLI that edits files in the workspace directly
          (claude, aider, ...). The curtain is the filesystem, so the isolation
          holds whoever the agent is.
  api   : a chat endpoint that only returns text. It cannot touch the filesystem,
          so it is told to emit each file in a delimited block and holdtrue writes
          the files, still only inside the workspace.

Either way the contract is the same: after run(), the expected files exist in the
workspace, and the provider was given nothing from outside it.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import signal
import subprocess
import threading
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Protocol, runtime_checkable

AGENT = "agent"
API = "api"


class ProviderError(RuntimeError):
    """A provider could not run: missing CLI, missing key, bad response."""


@runtime_checkable
class Provider(Protocol):
    """An LLM that writes the contract or the code. Either a coding-agent CLI that
    edits the workspace (kind == AGENT) or a chat endpoint that returns text for
    holdtrue to write (kind == API)."""
    name: str
    kind: str
    detail: str

    def available(self) -> bool: ...
    def models(self, timeout: float = 15.0) -> list[str]: ...
    def set_model(self, name: str) -> None: ...
    def run(self, prompt: str, workspace: Path, *, extra_dirs: tuple[Path, ...] = (),
            timeout: float = 300.0,
            on_output: Callable[[str], None] | None = None) -> str: ...


# --- the file-block protocol, used by api providers ---------------------------

_BLOCK = re.compile(
    r"<<<FILE\s+(?P<path>[^\n>]+?)\s*>>>\n(?P<body>.*?)\n<<<ENDFILE>>>",
    re.DOTALL,
)

OUTPUT_RULES = (
    "\n\nYou cannot edit files directly. Return every file you write, and nothing "
    "else, in this exact form (one block per file):\n"
    "<<<FILE relative/path.py>>>\n"
    "...the full contents of the file...\n"
    "<<<ENDFILE>>>\n"
    "Paths are relative to the project root. Do not wrap blocks in markdown fences."
)


def parse_file_blocks(text: str) -> list[tuple[str, str]]:
    """Pull (relative_path, contents) pairs out of a model's text response."""
    out: list[tuple[str, str]] = []
    for m in _BLOCK.finditer(text):
        out.append((m.group("path").strip(), m.group("body")))
    return out


def write_blocks(text: str, root: Path, allow: Callable[[str], bool]) -> list[str]:
    """Write the file blocks found in `text` under `root`. A path is written only
    if `allow(rel)` is true and it stays inside `root` (no traversal). Returns the
    list of relative paths written."""
    written: list[str] = []
    for rel, body in parse_file_blocks(text):
        rel = rel.lstrip("/")
        target = (root / rel).resolve()
        if not str(target).startswith(str(root.resolve()) + os.sep):
            continue  # escaped the workspace; drop it
        if not allow(rel):
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body, encoding="utf-8")
        written.append(rel)
    return written


# --- agent providers: a coding-agent CLI edits files in the workspace ----------

@dataclass
class CliAgent:
    name: str
    binary: str
    detail: str
    build_argv: Callable[[str, str, Path], list[str]]
    accepts_dirs: bool = False  # can it be granted read access to dirs outside cwd?
    # streaming: many CLIs only print their final answer, so reading stdout shows
    # nothing until the end. A tool with a real streaming mode supplies a different
    # argv for it, plus a parser that turns each output line into display text.
    stream_argv: Callable[[str, str, Path], list[str]] | None = None
    parse_line: Callable[[str], str | None] | None = None
    kind: str = AGENT

    def available(self) -> bool:
        return shutil.which(self.binary) is not None

    def models(self, timeout: float = 15.0) -> list[str]:
        return []  # a coding-agent CLI carries its own model choice

    def set_model(self, name: str) -> None:
        return None

    def run(self, prompt: str, workspace: Path, *, extra_dirs: tuple[Path, ...] = (),
            timeout: float = 300.0,
            on_output: Callable[[str], None] | None = None) -> str:
        exe = shutil.which(self.binary)
        if exe is None:
            raise ProviderError(f"{self.name}: '{self.binary}' not found on PATH")
        streaming = on_output is not None
        builder = self.stream_argv if (streaming and self.stream_argv) else self.build_argv
        argv = builder(exe, prompt, workspace)
        if self.accepts_dirs:
            for d in extra_dirs:
                argv += ["--add-dir", str(d)]
        if not streaming:
            try:
                p = subprocess.run(argv, cwd=str(workspace), capture_output=True,
                                   text=True, timeout=timeout)
            except subprocess.TimeoutExpired:
                raise ProviderError(f"{self.name}: timed out after {timeout:.0f}s")
            return (p.stdout or "") + (p.stderr or "")
        assert on_output is not None
        return self._run_streaming(argv, workspace, timeout, on_output)

    def _run_streaming(self, argv: list[str], workspace: Path, timeout: float,
                       on_output: Callable[[str], None]) -> str:
        from . import sandbox  # local: avoids a module-load cycle
        proc = subprocess.Popen(argv, cwd=str(workspace), stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, text=True, bufsize=1,
                                start_new_session=True)
        sandbox.track(proc)
        timed_out = threading.Event()

        def _kill() -> None:
            timed_out.set()
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            except Exception:
                proc.kill()

        killer = threading.Timer(timeout, _kill)
        killer.start()
        buf: list[str] = []
        try:
            assert proc.stdout is not None
            for line in proc.stdout:
                shown = self.parse_line(line) if self.parse_line else line
                if shown:
                    buf.append(shown)
                    try:
                        on_output(shown)
                    except Exception:
                        pass
            proc.wait()
        finally:
            killer.cancel()
            sandbox.untrack(proc)
        if timed_out.is_set():
            raise ProviderError(f"{self.name}: timed out after {timeout:.0f}s")
        return "".join(buf)


def _claude_argv(exe: str, prompt: str, ws: Path) -> list[str]:
    return [exe, "-p", prompt, "--add-dir", str(ws),
            "--allowed-tools", "Read Edit Write", "--permission-mode", "acceptEdits"]


def _claude_stream_argv(exe: str, prompt: str, ws: Path) -> list[str]:
    # stream-json emits one JSON event per step as it happens (text, tool calls),
    # instead of buffering the whole answer to the end. -p stream-json needs --verbose.
    return _claude_argv(exe, prompt, ws) + ["--output-format", "stream-json", "--verbose"]


def _claude_parse(line: str) -> str | None:
    """Turn one stream-json event into a short human-readable line for the run view."""
    line = line.strip()
    if not line:
        return None
    try:
        ev = json.loads(line)
    except json.JSONDecodeError:
        return line
    kind = ev.get("type")
    if kind == "assistant":
        out: list[str] = []
        for part in ev.get("message", {}).get("content", []):
            if part.get("type") == "text" and part.get("text"):
                out.append(part["text"].strip())
            elif part.get("type") == "tool_use":
                inp = part.get("input", {}) or {}
                target = inp.get("file_path") or inp.get("path") or inp.get("command") or ""
                out.append(f"→ {part.get('name', 'tool')} {target}".rstrip())
        return "\n".join(o for o in out if o) or None
    if kind == "result" and ev.get("subtype") not in ("success", None):
        return f"[{ev.get('subtype')}]"
    return None


def _aider_argv(exe: str, prompt: str, ws: Path) -> list[str]:
    return [exe, "--yes-always", "--no-auto-commits", "--no-stream", "--message", prompt]


def _gemini_argv(exe: str, prompt: str, ws: Path) -> list[str]:
    return [exe, "--yolo", "--prompt", prompt]


def _codex_argv(exe: str, prompt: str, ws: Path) -> list[str]:
    return [exe, "exec", "--full-auto", prompt]


def _custom_agent() -> CliAgent | None:
    """Wire any CLI via HOLDTRUE_AGENT_CMD, with {prompt} and {workspace}
    placeholders, e.g. HOLDTRUE_AGENT_CMD='mytool --dir {workspace} --msg {prompt}'."""
    tmpl = os.environ.get("HOLDTRUE_AGENT_CMD")
    if not tmpl:
        return None
    import shlex

    def argv(exe: str, prompt: str, ws: Path) -> list[str]:
        return [a.replace("{prompt}", prompt).replace("{workspace}", str(ws))
                for a in shlex.split(tmpl)]

    binary = shlex.split(tmpl)[0]
    return CliAgent("custom", binary, f"HOLDTRUE_AGENT_CMD ({binary})", argv)


# --- api providers: a chat endpoint returns text, holdtrue writes the files ----

def _http_json(url: str, headers: dict[str, str], payload: dict[str, Any],
               timeout: float) -> dict[str, Any]:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={**headers,
                                "content-type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            result: dict[str, Any] = json.loads(resp.read().decode("utf-8"))
            return result
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")[:300]
        raise ProviderError(f"HTTP {e.code} from {url}: {body}")
    except urllib.error.URLError as e:
        raise ProviderError(f"cannot reach {url}: {e.reason}")


def _http_get_json(url: str, headers: dict[str, str], timeout: float) -> dict[str, Any]:
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            result: dict[str, Any] = json.loads(resp.read().decode("utf-8"))
            return result
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")[:300]
        raise ProviderError(f"HTTP {e.code} from {url}: {body}")
    except urllib.error.URLError as e:
        raise ProviderError(f"cannot reach {url}: {e.reason}")


@dataclass
class ApiProvider:
    name: str
    detail: str
    env_key: str | None          # env var holding the credential (None = no key, e.g. ollama)
    model_env: str               # env var that overrides the model
    default_model: str
    caller: Callable[["ApiProvider", str, float], str]
    lister: Callable[["ApiProvider", float], list[str]] | None = None
    chosen: str | None = None    # model picked interactively, wins over env/default
    kind: str = API
    accepts_dirs: bool = False

    def model(self) -> str:
        return self.chosen or os.environ.get(self.model_env, self.default_model)

    def set_model(self, name: str) -> None:
        self.chosen = name or None

    def models(self, timeout: float = 15.0) -> list[str]:
        """The model ids the endpoint reports, best-effort. Empty if unknown."""
        if self.lister is None:
            return []
        try:
            return self.lister(self, timeout)
        except ProviderError:
            return []

    def available(self) -> bool:
        if self.env_key is None:
            return shutil.which("ollama") is not None or "OLLAMA_HOST" in os.environ
        return bool(os.environ.get(self.env_key))

    def run(self, prompt: str, workspace: Path, *, extra_dirs: tuple[Path, ...] = (),
            timeout: float = 300.0,
            on_output: Callable[[str], None] | None = None) -> str:
        text = self.caller(self, prompt, timeout)
        # The HTTP call is one shot, so the whole response lands at once. We still
        # surface it through on_output so the run view shows what the model wrote.
        if on_output and text:
            try:
                on_output(text)
            except Exception:
                pass
        return text


def _anthropic_call(p: ApiProvider, prompt: str, timeout: float) -> str:
    key = os.environ.get(p.env_key or "")
    if not key:
        raise ProviderError(f"{p.name}: set {p.env_key}")
    out = _http_json("https://api.anthropic.com/v1/messages",
                     {"x-api-key": key, "anthropic-version": "2023-06-01"},
                     {"model": p.model(), "max_tokens": 4096,
                      "messages": [{"role": "user", "content": prompt}]}, timeout)
    parts = out.get("content", [])
    return "".join(b.get("text", "") for b in parts if b.get("type") == "text")


def _openai_call(p: ApiProvider, prompt: str, timeout: float) -> str:
    key = os.environ.get(p.env_key or "")
    if not key:
        raise ProviderError(f"{p.name}: set {p.env_key}")
    base = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
    out = _http_json(f"{base}/chat/completions",
                     {"authorization": f"Bearer {key}"},
                     {"model": p.model(),
                      "messages": [{"role": "user", "content": prompt}]}, timeout)
    return str(out["choices"][0]["message"]["content"])


def _ollama_host() -> str:
    host = os.environ.get("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
    return host if host.startswith("http") else "http://" + host


def _ollama_call(p: ApiProvider, prompt: str, timeout: float) -> str:
    out = _http_json(f"{_ollama_host()}/api/chat", {},
                     {"model": p.model(), "stream": False,
                      "messages": [{"role": "user", "content": prompt}]}, timeout)
    return str(out.get("message", {}).get("content", ""))


def _anthropic_models(p: ApiProvider, timeout: float) -> list[str]:
    key = os.environ.get(p.env_key or "")
    if not key:
        return []
    out = _http_get_json("https://api.anthropic.com/v1/models",
                         {"x-api-key": key, "anthropic-version": "2023-06-01"}, timeout)
    return [m["id"] for m in out.get("data", []) if "id" in m]


def _openai_models(p: ApiProvider, timeout: float) -> list[str]:
    key = os.environ.get(p.env_key or "")
    if not key:
        return []
    base = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
    out = _http_get_json(f"{base}/models", {"authorization": f"Bearer {key}"}, timeout)
    ids = [m["id"] for m in out.get("data", []) if "id" in m]
    chat = sorted(i for i in ids if i.startswith(("gpt", "o1", "o3", "o4", "chatgpt")))
    return chat or sorted(ids)


def _ollama_models(p: ApiProvider, timeout: float) -> list[str]:
    out = _http_get_json(f"{_ollama_host()}/api/tags", {}, timeout)
    return [m["name"] for m in out.get("models", []) if "name" in m]


# --- registry + discovery ------------------------------------------------------

def _registry() -> list[Provider]:
    providers: list[Provider] = [
        CliAgent("claude", "claude", "claude CLI (reuses your session)",
                 _claude_argv, accepts_dirs=True,
                 stream_argv=_claude_stream_argv, parse_line=_claude_parse),
        CliAgent("aider", "aider", "aider CLI (best-effort)", _aider_argv),
        CliAgent("gemini", "gemini", "gemini CLI (best-effort)", _gemini_argv),
        CliAgent("codex", "codex", "codex CLI (best-effort)", _codex_argv),
        ApiProvider("anthropic-api", "Anthropic API (needs ANTHROPIC_API_KEY)",
                    "ANTHROPIC_API_KEY", "HOLDTRUE_ANTHROPIC_MODEL",
                    "claude-sonnet-4-6", _anthropic_call, lister=_anthropic_models),
        ApiProvider("openai-api", "OpenAI API (needs OPENAI_API_KEY)",
                    "OPENAI_API_KEY", "HOLDTRUE_OPENAI_MODEL", "gpt-4o", _openai_call,
                    lister=_openai_models),
        ApiProvider("ollama", "Ollama (local, needs the ollama daemon)", None,
                    "HOLDTRUE_OLLAMA_MODEL", "llama3.1", _ollama_call, lister=_ollama_models),
    ]
    custom = _custom_agent()
    if custom is not None:
        providers.insert(1, custom)
    return providers


def all_providers() -> list[Provider]:
    return _registry()


def discover() -> list[Provider]:
    """The providers that look usable right now (CLI on PATH, or key/daemon present)."""
    return [p for p in _registry() if p.available()]


def get(name: str) -> Provider:
    for p in _registry():
        if p.name == name:
            return p
    raise ProviderError(f"unknown provider '{name}'")


def resolve(name: str | None) -> Provider:
    """Pick a provider by name, or the best available default (claude first)."""
    if name:
        p = get(name)
        if not p.available():
            raise ProviderError(f"provider '{name}' is not available: {p.detail}")
        return p
    avail = discover()
    if not avail:
        raise ProviderError("no LLM provider available (no agent CLI, no API key)")
    for p in avail:
        if p.name == "claude":
            return p
    return avail[0]
