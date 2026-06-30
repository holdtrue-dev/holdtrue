"""holdtrue studio: an interactive TUI for the whole loop.

It discovers the LLM providers that look usable, lets you pick one (and, for an
API provider, which model), gives you a field to type an intent, then runs the
loop live: the author writes the contract, holdtrue self-checks it against the
reference oracle, you approve it, the implementer fills it in behind the curtain,
and it gets verified. The verdict, with its evidence, lands at the end.

Screens: pick a provider, (pick a model), write the intent, watch it run. The run
view is a stage tracker (round markers, a spinner and clock on the active stage)
with the verify checks broken out below as a drill-in table, so the two levels
never blur together.
"""
from __future__ import annotations

import tempfile
import threading
import time
from pathlib import Path

from rich.markup import escape
from rich.text import Text
from textual.app import App, ComposeResult
from textual.containers import Vertical, VerticalScroll
from textual.screen import ModalScreen, Screen
from textual.widgets import (Button, DataTable, Footer, Input, Markdown,
                             OptionList, RichLog, Static, TextArea)

from . import (agents, changelog, engine, providers, report, revise, sandbox,
               verify)
from .classify import ENFORCED, FAILED, GUARANTEED, UNGUARANTEED
from .tui import CheckDetail, _BANNER, _COLOR, _ICON, _LABEL

_HOURGLASS = ("⏳", "⌛")

_OK = "#33ff66"
_WARN = "#f3c54e"
_BAD = "#ff5f5f"
_DIM = "#7e9387"
_QUEUED = "#3a4a40"
_RUN = "#f3c54e"
_INK = "#cdddd2"
_ENF = "#2bd6c0"
_TOOL_COLOR = {"Bash": "#f3c54e", "Write": "#33ff66", "Edit": "#33ff66",
               "Read": "#2bd6c0", "Grep": "#2bd6c0", "Glob": "#2bd6c0",
               "TodoWrite": "#7e9387", "WebFetch": "#9fd0ff", "WebSearch": "#9fd0ff"}
_VERDICT_COLOR = {GUARANTEED: _OK, ENFORCED: _ENF, UNGUARANTEED: _WARN, FAILED: _BAD}
_VERDICT_GLYPH = {GUARANTEED: "✓", ENFORCED: "⊨", UNGUARANTEED: "~", FAILED: "✗"}
_VERDICT_MEANING = {
    GUARANTEED: "proven over all inputs; the contract caught injected bugs and rejected broken stand-ins.",
    ENFORCED: "checked at runtime on every call and clean over every sample, but not proven over all inputs.",
    UNGUARANTEED: "only sampled evidence, not a proof. still needs human review.",
    FAILED: "a counterexample was found: the contract does not hold.",
}

_STAGES = [
    ("author", "author", "write the contract"),
    ("selfcheck", "self-check", "does it hold for the oracle?"),
    ("approve", "approve", "your call"),
    ("implement", "implement", "write the code, blind"),
    ("verify", "verify", "prove it, sandboxed"),
]


class ProviderScreen(Screen):
    """Pick which LLM writes the contract and the code."""

    CSS = """
    ProviderScreen { align: center middle; }
    #logo { color: #33ff66; text-style: bold; padding: 1 2 0 2; }
    #intro { color: #7e9387; padding: 0 2 1 2; }
    OptionList { width: 84; max-width: 90%; max-height: 12; border: round #2bbf57; background: #0c120c; }
    #hint { color: #506054; padding: 0 2; }
    #none { color: #ff5f5f; padding: 1 2; }
    #go { margin: 1 2; }
    """
    BINDINGS = [("q", "quit_app", "quit")]

    def compose(self) -> ComposeResult:
        yield Static(_BANNER, id="logo")
        yield Static("studio: pick a provider, then write an intent.", id="intro")
        found = self.app._providers  # type: ignore[attr-defined]
        if not found:
            yield Static("no provider available. install a coding-agent CLI (claude, "
                         "aider, ...) or set an API key, then run studio again.", id="none")
            return
        yield OptionList(*[f"{p.name}  ({p.kind}) - {p.detail}" for p in found],
                         id="providers")
        yield Static("up/down to choose, enter to continue", id="hint")
        yield Button("continue", variant="success", id="go")
        yield Footer()

    def on_mount(self) -> None:
        if self.app._providers:  # type: ignore[attr-defined]
            self.query_one("#providers", OptionList).focus()

    def action_quit_app(self) -> None:
        self.app.exit()

    def _choose(self, idx: int) -> None:
        provider = self.app._providers[idx]  # type: ignore[attr-defined]
        self.app._provider = provider        # type: ignore[attr-defined]
        if provider.kind == providers.API:
            self.app.push_screen(ModelScreen())
        else:
            self.app.push_screen(IntentScreen())

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        self._choose(event.option_index)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        ol = self.query_one("#providers", OptionList)
        self._choose(ol.highlighted or 0)


class ModelScreen(Screen):
    """For an API provider, pick which model. The list is what the endpoint reports;
    you can also type a model id, or take the default."""

    CSS = """
    ModelScreen { align: center middle; }
    #mwrap { width: 84; max-width: 92%; height: auto; }
    #mhead { color: #33ff66; text-style: bold; padding: 0 0 1 0; }
    #mstatus { color: #7e9387; padding: 0 0 1 0; }
    OptionList { height: 12; border: round #2bbf57; background: #0c120c; }
    #mmanual { margin: 1 0 0 0; }
    """
    BINDINGS = [("escape", "back", "back"), ("q", "quit_app", "quit")]

    def compose(self) -> ComposeResult:
        prov = self.app._provider  # type: ignore[attr-defined]
        with Vertical(id="mwrap"):
            yield Static(f"model for {prov.name}", id="mhead")
            yield Static("fetching available models ...", id="mstatus")
            yield OptionList(id="models")
            yield Input(placeholder=f"or type a model id, then enter "
                        f"(default: {prov.default_model})", id="mmanual")
        yield Footer()

    def on_mount(self) -> None:
        self._ids: list[str] = []
        threading.Thread(target=self._fetch, daemon=True).start()

    def _fetch(self) -> None:
        prov = self.app._provider  # type: ignore[attr-defined]
        try:
            found = prov.models()
        except Exception:
            found = []
        self.app.call_from_thread(self._populate, found)

    def _populate(self, found: list[str]) -> None:
        prov = self.app._provider  # type: ignore[attr-defined]
        self._ids = [prov.default_model] + [m for m in found if m != prov.default_model]
        ol = self.query_one("#models", OptionList)
        ol.clear_options()
        ol.add_option(f"default  ({prov.default_model})")
        for m in self._ids[1:]:
            ol.add_option(m)
        status = self.query_one("#mstatus", Static)
        if found:
            status.update(f"{len(found)} models available. enter to pick, or type one below.")
        else:
            status.update("could not list models. use the default, or type a model id below.")
        ol.focus()

    def action_back(self) -> None:
        self.app.pop_screen()

    def action_quit_app(self) -> None:
        self.app.exit()

    def _go(self, model: str) -> None:
        self.app._provider.set_model(model)  # type: ignore[attr-defined]
        self.app.push_screen(IntentScreen())

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        idx = event.option_index
        self._go("" if idx == 0 else self._ids[idx])  # index 0 == default

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self._go(event.value.strip())


class IntentScreen(Screen):
    """Type the intent in plain language, then kickstart the loop."""

    CSS = """
    IntentScreen { align: center middle; }
    #wrap { width: 90; max-width: 94%; height: auto; }
    #head { color: #33ff66; text-style: bold; padding: 0 0 1 0; }
    #pname { margin: 0 0 1 0; }
    TextArea { height: 10; border: round #2bbf57; }
    #start { margin: 1 0 0 0; }
    """
    BINDINGS = [("escape", "back", "back"), ("ctrl+s", "start", "start")]

    def compose(self) -> ComposeResult:
        prov = self.app._provider  # type: ignore[attr-defined]
        model = getattr(prov, "chosen", None)
        who = f"{prov.name}" + (f" / {model}" if model else "")
        with Vertical(id="wrap"):
            yield Static(f"intent  (provider: {who})\n"
                         "describe one function in plain language. it must take and return "
                         "integers, with no files, randomness, or side effects (that is what "
                         "holdtrue can prove today).", id="head")
            yield Input(placeholder="project name (optional, e.g. my_intent)", id="pname")
            yield TextArea("", id="intent")
            yield Button("start  (ctrl+s)", variant="success", id="start")
        yield Footer()

    def action_back(self) -> None:
        self.app.pop_screen()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.action_start()

    def action_start(self) -> None:
        intent = self.query_one("#intent", TextArea).text.strip()
        if not intent:
            return
        name = self.query_one("#pname", Input).value.strip()
        self.app.start_run(name, intent)  # type: ignore[attr-defined]


class RunScreen(Screen):
    """Watch the loop run: a stage pipeline with round markers and a live spinner,
    the contract you approve, the verify checks as a drill-in table, and a verdict
    panel with its evidence."""

    CSS = """
    RunScreen { layout: vertical; }
    #logo { color: #33ff66; text-style: bold; padding: 1 2 0 2; }
    #rhead { padding: 0 2 0 2; color: #2bbf57; }
    #body { height: 1fr; }
    #stages { margin: 1 2 0 2; height: auto; background: #07090a; scrollbar-size: 0 0; }
    #output { margin: 1 2 0 2; height: 16; border: round #18241d; background: #0a0f0a;
              color: #9fb3a6; display: none; }
    #contract { margin: 1 2 0 2; border: round #2bbf57; background: #0c120c; padding: 1 2;
                height: auto; display: none; }
    #checks-label { margin: 1 2 0 2; color: #506054; display: none; }
    #checks { margin: 0 2 1 2; height: auto; background: #07090a; display: none; }
    #checks > .datatable--cursor { background: #14201a; }
    #approve { margin: 0 2 1 2; display: none; }
    #approve.ready { display: block; }
    #verdict { margin: 0 2 1 2; padding: 1 2; text-align: left;
               border: heavy #18241d; color: #7e9387; height: auto; }
    """
    BINDINGS = [("a", "approve", "approve"), ("d", "decline", "decline"),
                ("r", "report", "report"), ("q", "quit_app", "quit")]

    def compose(self) -> ComposeResult:
        app = self.app
        prov = app._provider  # type: ignore[attr-defined]
        model = getattr(prov, "chosen", None)
        who = prov.name + (f" / {model}" if model else "")
        proj = app._project.name if app._project else "intent"  # type: ignore[attr-defined]
        yield Static(_BANNER, id="logo")
        yield Static(f"{proj}    provider: {who}    "
                     "[#506054]· enter on a stage or check to drill in ·[/]", id="rhead")
        with VerticalScroll(id="body"):
            yield DataTable(id="stages", show_header=False, cursor_type="row")
            yield RichLog(id="output", highlight=False, markup=False, wrap=True, max_lines=2000)
            yield Static("", id="contract")
            yield Static("verify · checks  (↑↓ to move, enter to drill in)", id="checks-label")
            yield DataTable(id="checks", show_header=False, cursor_type="row")
        yield Button("approve the contract & implement  (a)", variant="success", id="approve")
        yield Static("running the loop ...", id="verdict")
        yield Footer()

    def on_mount(self) -> None:
        self._gate = threading.Event()
        self._gate_choice: str | None = None
        self._active: str | None = None
        self._t0 = 0.0
        self._spin_i = 0
        self._status: dict[str, str] = {}
        self._note: dict[str, str] = {}
        self._results: dict[str, engine.CheckResult] = {}
        self._report_md: str | None = None
        self._detail: dict[str, str] = {}      # per-stage markdown, for drill-down
        self._stream_target: str | None = None
        t = self.query_one("#stages", DataTable)
        t.add_column(" ", width=3, key="icon")
        t.add_column("stage", width=12, key="name")
        t.add_column("note", width=64, key="note")
        for key, label, _hint in _STAGES:
            self._status[key] = "queued"
            self._note[key] = ""
            t.add_row(Text("○", style=_QUEUED), Text(label, style=_QUEUED),
                      Text("", style=_DIM), key=key)
        t.focus()
        self.set_interval(0.12, self._spin)
        if getattr(self.app, "_autorun", True):
            threading.Thread(target=self._pipeline, daemon=True).start()

    # --- ui updates, all on the main thread ---
    def _spin(self) -> None:
        if not self._active:
            return
        self._spin_i += 1
        glass = _HOURGLASS[(self._spin_i // 4) % 2]  # a flipping hourglass in the marker
        e = time.monotonic() - self._t0
        clock = f"{int(e) // 60}:{int(e) % 60:02d}"  # fixed width, so it stays put
        t = self.query_one("#stages", DataTable)
        t.update_cell(self._active, "icon", Text(glass, style=_RUN))
        t.update_cell(self._active, "note",
                      Text(f"{self._note[self._active]}   {clock}", style=_RUN))

    def _stage(self, key: str, status: str, note: str = "") -> None:
        self._status[key] = status
        self._note[key] = note
        if status == "running":
            self._active = key
            self._t0 = time.monotonic()
        elif self._active == key:
            self._active = None
        # round markers for the pipeline, deliberately not the check marks below
        icon, color = {
            "queued": ("○", _QUEUED), "running": (_HOURGLASS[0], _RUN),
            "waiting": ("▸", _WARN), "done": ("●", _OK), "failed": ("✕", _BAD),
        }[status]
        label = dict((k, lab) for k, lab, _h in _STAGES)[key]
        name_style = _INK if status in ("running", "done", "waiting") else (_BAD if status == "failed" else _QUEUED)
        note_style = _RUN if status == "running" else (_WARN if status == "waiting" else _DIM)
        t = self.query_one("#stages", DataTable)
        t.update_cell(key, "icon", Text(icon, style=color))
        t.update_cell(key, "name", Text(label, style=name_style))
        t.update_cell(key, "note", Text(note, style=note_style))

    def _stream_begin(self, stage: str, title: str) -> None:
        self._stream_target = stage
        self._detail[stage] = ""
        self.query_one("#contract", Static).styles.display = "none"
        self.query_one("#checks-label", Static).styles.display = "none"
        self.query_one("#checks", DataTable).styles.display = "none"
        out = self.query_one("#output", RichLog)
        out.clear()
        out.styles.display = "block"
        out.write(f"── {title} ──")

    def _stream_write(self, text: str) -> None:
        out = self.query_one("#output", RichLog)
        for line in text.split("\n"):
            out.write(self._style_line(line))
            if self._stream_target is not None:
                self._detail[self._stream_target] += self._md_line(line) + "\n"

    def _style_line(self, line: str) -> Text:
        """A model output line. Tool calls (Read/Write/Edit/Bash ...) get their tool
        name highlighted so the actions stand out from the narration."""
        if line.startswith("→ "):  # "-> Name target", from the stream-json parser
            name, _, tail = line[2:].partition(" ")
            t = Text("→ ", style=_DIM)
            t.append(name, style=f"bold {_TOOL_COLOR.get(name, _ENF)}")
            if tail:
                t.append("  ·  ", style=_DIM)
                t.append(tail if len(tail) <= 160 else tail[:159] + "…", style="#9fb3a6")
            return t
        return Text(line, style="#cfe0d4")

    @staticmethod
    def _md_line(line: str) -> str:
        if line.startswith("→ "):
            name, _, tail = line[2:].partition(" ")
            return f"- **{name}**" + (f" `{tail}`" if tail else "")
        return line

    def _show_contract(self, signature: str, decorators: list[str]) -> None:
        self.query_one("#output", RichLog).styles.display = "none"
        block = "\n".join([signature, *decorators])
        self._detail["approve"] = ("The implementer sees only this. You approve it before "
                                   "anything is written.\n\n```python\n" + block + "\n```\n")
        lines = ["[#cdddd2]the contract you are approving[/]", "",
                 f"[#7fd6a0]{signature}[/]"]
        lines += [f"[#33ff66]{d}[/]" for d in decorators]
        c = self.query_one("#contract", Static)
        c.update("\n".join(lines))
        c.styles.display = "block"

    def _set_detail(self, stage: str, md: str) -> None:
        self._detail[stage] = md

    @staticmethod
    def _checks_md(results: dict[str, engine.CheckResult]) -> str:
        return "\n".join(f"- **{_LABEL.get(k, k)}** ({r.status}) — {r.detail}"
                         + (f"\n  - counterexample: `{r.counterexample}`" if r.counterexample else "")
                         for k, r in results.items())

    def _checks_begin(self, order: list[str]) -> None:
        self.query_one("#output", RichLog).styles.display = "none"
        self.query_one("#contract", Static).styles.display = "none"
        self.query_one("#checks-label", Static).styles.display = "block"
        t = self.query_one("#checks", DataTable)
        t.styles.display = "block"
        t.clear(columns=True)
        t.add_column(" ", width=3, key="icon")
        t.add_column("check", width=22, key="check")
        t.add_column("status", width=11, key="status")
        t.add_column("detail", width=52, key="detail")
        for k in order:
            t.add_row(Text("·", style=_QUEUED), Text(_LABEL.get(k, k)),
                      Text("queued", style=_QUEUED), Text(""), key=k)
        t.focus()

    def _update_check(self, r: engine.CheckResult) -> None:
        self._results[r.kind] = r
        color = _COLOR.get(r.status, _DIM)
        detail = r.detail if len(r.detail) <= 50 else r.detail[:49] + "…"
        t = self.query_one("#checks", DataTable)
        try:
            t.update_cell(r.kind, "icon", Text(_ICON.get(r.status, "·"), style=color))
            t.update_cell(r.kind, "status", Text(r.status, style=color))
            t.update_cell(r.kind, "detail", Text(detail, style="#9fb3a6"))
        except Exception:
            pass

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        key = event.row_key.value
        if event.data_table.id == "checks":
            r = self._results.get(key)
            if r is not None:
                self.app.push_screen(CheckDetail(r))
            return
        # a stage row: drill into what it produced
        label = dict((k, lab) for k, lab, _h in _STAGES).get(key, key)
        md = self._detail.get(key) or "_this stage has not produced anything yet._"
        self.app.push_screen(MarkdownScreen(f"stage · {label}", md))

    def _ask(self, label: str) -> None:
        """Show the action button with a label and arm the approval gate."""
        b = self.query_one("#approve", Button)
        b.label = label
        b.add_class("ready")
        b.focus()
        self._gate_choice = None
        self._gate.clear()

    def _show_revision(self, diff: str, note: str) -> None:
        self.query_one("#output", RichLog).styles.display = "none"
        lines = ["[#f3c54e]proposed contract revision[/]", "",
                 f"[#9fb3a6]{escape(diff) if diff else '(no change to the proven lines)'}[/]",
                 "", f"[#7e9387]why:[/] {escape(note)}"]
        c = self.query_one("#contract", Static)
        c.update("\n".join(lines))
        c.styles.display = "block"

    def _set_verdict(self, markup: str, color: str) -> None:
        self.query_one("#approve", Button).remove_class("ready")
        v = self.query_one("#verdict", Static)
        v.update(markup)
        v.styles.color = color
        v.styles.border = ("heavy", color)
        v.styles.opacity = 0.0
        v.styles.animate("opacity", value=1.0, duration=0.5)

    # --- input ---
    def _resolve_gate(self, choice: str) -> None:
        b = self.query_one("#approve", Button)
        if b.has_class("ready"):
            self._gate_choice = choice
            b.remove_class("ready")
            self._gate.set()

    def action_approve(self) -> None:
        self._resolve_gate("approve")

    def action_decline(self) -> None:
        self._resolve_gate("decline")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.action_approve()

    def action_report(self) -> None:
        if self._report_md:
            self.app.push_screen(MarkdownScreen("evidence report", self._report_md))

    def action_quit_app(self) -> None:
        self.app._quitting = True  # type: ignore[attr-defined]
        self._gate.set()
        sandbox.abort_all()
        self.app.exit()

    def _await_gate(self) -> str | None:
        """Block the worker thread until the user approves/declines, or quits."""
        while not self._gate.wait(0.2):
            if getattr(self.app, "_quitting", False):
                return None
        return self._gate_choice

    def _safe(self, fn, *a) -> None:  # noqa: ANN001
        if getattr(self.app, "_quitting", False):
            return
        try:
            self.app.call_from_thread(fn, *a)
        except Exception:
            pass

    def _verdict_markup(self, cls, report_path: Path) -> str:  # noqa: ANN001
        color = _VERDICT_COLOR.get(cls.classification, _DIM)
        glyph = _VERDICT_GLYPH.get(cls.classification, "·")
        human = "YES" if cls.requires_human_code_review else "no"
        lines = [f"[b {color}]{glyph}  {cls.classification}[/]",
                 f"[{_DIM}]{_VERDICT_MEANING.get(cls.classification, '')}[/]", ""]
        lines.append(f"[{_DIM}]deciding:[/] {cls.deciding_check}")
        for reason in cls.reasons[:4]:
            lines.append(f"[{_DIM}]  - {reason}[/]")
        lines.append(f"[{_DIM}]human code review still required:[/] {human}")
        lines.append(f"[{_DIM}]press [/][b]r[/][{_DIM}] to read the full evidence report.[/]")
        return "\n".join(lines)

    def _selfcheck_loop(self, project: Path, manifest: dict, provider, stream):  # noqa: ANN001
        """Self-check; on failure, propose a revision and (with approval) apply it,
        bounded. Returns the manifest to proceed with, or None to stop (verdict set)."""
        for attempt in range(3):
            self._safe(self._stage, "selfcheck", "running", "checking against the oracle")
            ok, why = revise.self_check(project, manifest)
            if ok:
                self._safe(self._stage, "selfcheck", "done", "holds for the oracle")
                self._safe(self._set_detail, "selfcheck",
                           "The reference oracle was run against the contract; it must hold, "
                           "provably and non-vacuously, before any code is written.")
                return manifest
            self._safe(self._stage, "selfcheck", "failed", "contract does not hold")
            if attempt >= 2:
                self._safe(self._set_verdict, "[b #ff5f5f]✕  WRONG CONTRACT[/]\n"
                           "[#7e9387]still failing after revisions.[/]", _BAD)
                return None
            self._safe(self._stream_begin, "selfcheck", "revising the contract")
            staged = revise.stage_contract(project, Path(tempfile.mkdtemp(prefix="holdtrue_studio_revise_")))
            revise.spawn_reviser(staged, manifest, why, provider, on_output=stream)
            if not (staged / "contract" / "manifest.yaml").exists():
                self._safe(self._set_verdict, "[b #ff5f5f]✕  NO REVISION[/]\n"
                           "[#7e9387]the reviser produced no contract.[/]", _BAD)
                return None
            new_manifest = verify.load_manifest(staged, "contract/manifest.yaml")
            ok2, reason = revise.not_weaker(staged, manifest, new_manifest)
            diff, note = revise.contract_diff(manifest, new_manifest), revise.justification(staged)
            self._safe(self._show_revision, diff, note)
            self._safe(self._set_detail, "selfcheck",
                       "## proposed revision\n\n```diff\n" + diff + "\n```\n\n" + note)
            if not ok2:
                changelog.record(project, trigger="self-check", evidence=why, diff=diff,
                                 justification=note, approved_by="refused (ratchet)", applied=False)
                self._safe(self._set_verdict, "[b #ff5f5f]✕  REVISION REFUSED[/]\n"
                           f"[#7e9387]{escape(reason)}. never weaken a check to pass.[/]", _BAD)
                return None
            self._safe(self._stage, "selfcheck", "waiting", "approve the revision: a / decline: d")
            self._safe(self._ask, "approve the contract revision  (a)   ·   decline (d)")
            choice = self._await_gate()
            if choice is None:
                return None
            applied = choice == "approve"
            changelog.record(project, trigger="self-check", evidence=why, diff=diff,
                             justification=note,
                             approved_by="human" if applied else "human (declined)", applied=applied)
            if not applied:
                self._safe(self._set_verdict, "[b #f3c54e]REVISION DECLINED[/]\n"
                           "[#7e9387]the contract was not changed.[/]", _WARN)
                return None
            revise.apply(staged, project)
            manifest = verify.load_manifest(project, "contract/manifest.yaml")
        return None

    # --- the loop, on a daemon thread ---
    def _pipeline(self) -> None:
        app = self.app
        project: Path = app._project          # type: ignore[attr-defined]
        template: Path = app._template        # type: ignore[attr-defined]
        provider = app._provider              # type: ignore[attr-defined]
        stream = lambda s: self._safe(self._stream_write, s)  # noqa: E731
        try:
            self._safe(self._stage, "author", "running", "writing the contract")
            self._safe(self._stream_begin, "author", "author")
            agents.spawn_author(project, template, provider, on_output=stream)
            if not (project / "contract" / "manifest.yaml").exists():
                self._safe(self._stage, "author", "failed", "produced no contract")
                self._safe(self._set_verdict, "[b #ff5f5f]✕  NO CONTRACT[/]\n"
                           "[#7e9387]the author wrote no contract/manifest.yaml.[/]", _BAD)
                return
            manifest = verify.load_manifest(project, "contract/manifest.yaml")
            self._safe(self._stage, "author", "done", "contract written")

            revised = self._selfcheck_loop(project, manifest, provider, stream)
            if revised is None:
                return  # verdict already set, or quit
            manifest = revised

            decos = manifest.get("checks", {}).get("crosshair", {}).get("decorators", [])
            self._safe(self._show_contract, manifest.get("signature", ""), decos)
            self._safe(self._stage, "approve", "waiting", "your call (press a)")
            self._safe(self._ask, "approve the contract & implement  (a)")
            if self._await_gate() != "approve":
                if getattr(app, "_quitting", False):
                    return
                self._safe(self._stage, "approve", "failed", "declined")
                self._safe(self._set_verdict, "[b #f3c54e]CONTRACT DECLINED[/]\n"
                           "[#7e9387]you did not approve the contract.[/]", _WARN)
                return
            self._safe(self._stage, "approve", "done", "approved")

            ws = Path(tempfile.mkdtemp(prefix="holdtrue_studio_impl_"))
            agents.stage_workspace(project, manifest, ws)
            order = ["types", "crosshair", "hypothesis_shown", "hypothesis_heldout", "negative_probe"]
            if app._mutation:  # type: ignore[attr-defined]
                order.append("mutation")
            feedback, results, cls = None, None, None
            for rnd in range(1, 4):
                if getattr(app, "_quitting", False):
                    return
                note = "writing the code, blind" + (f" (round {rnd})" if rnd > 1 else "")
                self._safe(self._stage, "implement", "running", note)
                self._safe(self._stream_begin, "implement", f"implement (round {rnd})")
                impl_path, _ = agents.spawn_implementer(ws, manifest, provider,
                                                        feedback=feedback, on_output=stream)
                if not impl_path.exists() or "NotImplementedError" in impl_path.read_text():
                    self._safe(self._stage, "implement", "failed", "produced nothing")
                    self._safe(self._set_verdict, "[b #ff5f5f]✕  NO IMPLEMENTATION[/]\n"
                               "[#7e9387]the implementer wrote no code.[/]", _BAD)
                    return
                self._safe(self._stage, "implement", "done", "code written")
                self._safe(self._stage, "verify", "running", "proving it, sandboxed")
                self._safe(self._checks_begin, order)
                results, cls = verify.run_verification(
                    project, impl_path, manifest,
                    sandbox_on=app._sandbox_on, mutation=app._mutation,  # type: ignore[attr-defined]
                    on_result=lambda r: self._safe(self._update_check, r))
                if cls.classification != FAILED:
                    self._safe(self._stage, "verify", "done", cls.classification.lower())
                    break
                self._safe(self._stage, "verify", "failed", "counterexample found")
                cex = results.get("crosshair").counterexample if results.get("crosshair") else None
                feedback = f"{cls.evidence}" + (f" counterexample: {cex}" if cex else "")

            if cls is not None and results is not None:
                detail = self._checks_md(results)
                if cls.classification == FAILED:
                    self._safe(self._stream_begin, "verify", "diagnosing why it is stuck")
                    cx = results.get("crosshair").counterexample if results.get("crosshair") else None
                    evidence = (cls.evidence or "") + (f" counterexample: {cx}" if cx else "")
                    diag = revise.diagnose(project, evidence, provider, on_output=stream)
                    changelog.record(project, trigger="failed-exhausted", evidence=evidence or "(none)",
                                     diff="", justification=diag,
                                     approved_by="diagnosis (not applied)", applied=False)
                    detail = "## why it is stuck\n\n" + diag + "\n\n---\n\n" + detail
                self._safe(self._set_detail, "verify",
                           "The implementation, checked behind the curtain (sandboxed). Select a "
                           "row to drill into a check.\n\n" + detail)
                report_path = self._write_report(project, manifest, results, cls)
                self._safe(self._set_verdict, self._verdict_markup(cls, report_path),
                           _VERDICT_COLOR.get(cls.classification, _DIM))
        except providers.ProviderError as e:
            self._safe(self._set_verdict, f"[b #ff5f5f]✕  PROVIDER ERROR[/]\n[#7e9387]{e}[/]", _BAD)
        except Exception as e:  # noqa: BLE001 - surface any failure on the verdict line
            self._safe(self._set_verdict, f"[b #ff5f5f]✕  ERROR[/]\n[#7e9387]{e}[/]", _BAD)

    def _write_report(self, project, manifest, results, cls) -> Path:  # noqa: ANN001
        sb = self.app._sandbox_on and engine.sandbox.bwrap_available()  # type: ignore[attr-defined]
        rep = report.build_report(manifest, "studio", results, cls, sandboxed=sb)
        out_dir = project / "reports"
        out_dir.mkdir(exist_ok=True)
        (out_dir / "evidence_report.json").write_text(report.to_json(rep), encoding="utf-8")
        md = out_dir / "evidence_report.md"
        md_text = report.render_md(rep)
        md.write_text(md_text, encoding="utf-8")
        self._report_md = md_text
        return md


class MarkdownScreen(ModalScreen):
    """A titled, scrollable, rendered-markdown overlay: the evidence report, or
    whatever a stage produced (the model's own output included)."""

    BINDINGS = [("escape", "dismiss", "back"), ("q", "dismiss", "back")]
    CSS = """
    MarkdownScreen { align: center middle; }
    #mdhead { color: #33ff66; text-style: bold; padding: 0 2; }
    #rbox { width: 90%; height: 82%; border: round #2bbf57; background: #0c120c; padding: 1 2; }
    #rfoot { color: #506054; padding: 0 2; }
    """

    def __init__(self, title: str, md: str) -> None:
        super().__init__()
        self._title = title
        self._md = md

    def compose(self) -> ComposeResult:
        yield Static(self._title, id="mdhead")
        with VerticalScroll(id="rbox"):
            yield Markdown(self._md)
        yield Static("esc to go back", id="rfoot")

    def action_dismiss(self) -> None:  # type: ignore[override]
        self.app.pop_screen()


class StudioApp(App):
    CSS = "Screen { background: #07090a; color: #cdddd2; }"

    def __init__(self, project: Path | None, template: Path, *,
                 sandbox_on: bool, mutation: bool, autorun: bool = True,
                 provider_name: str | None = None, model: str | None = None,
                 name: str | None = None, intent: str | None = None) -> None:
        super().__init__()
        self._project = project
        self._template = template
        self._sandbox_on = sandbox_on
        self._mutation = mutation
        self._autorun = autorun
        self._providers = providers.discover()
        self._provider = self._providers[0] if self._providers else None
        self._provider_name = provider_name
        self._model = model
        self._name = name
        self._intent = intent
        self._quitting = False

    def on_mount(self) -> None:
        # The picker is always the base screen, so 'back' has somewhere to go. Anything
        # supplied on the command line skips ahead on top of it.
        self.push_screen(ProviderScreen())
        if not self._provider_name:
            return
        try:
            prov = providers.resolve(self._provider_name)
        except providers.ProviderError:
            return  # named provider not usable: stay on the picker
        self._provider = prov
        if self._model:
            prov.set_model(self._model)
        if prov.kind == providers.API and not self._model:
            self.push_screen(ModelScreen())
        elif self._intent:
            self.start_run(self._name or "", self._intent)
        else:
            self.push_screen(IntentScreen())

    def start_run(self, name: str, intent: str) -> None:
        project = self._project
        if project is None:
            base = Path(tempfile.mkdtemp(prefix="holdtrue_studio_"))
            project = base / name if name else base
        project.mkdir(parents=True, exist_ok=True)
        (project / "intent").mkdir(parents=True, exist_ok=True)
        (project / "intent" / "intent.md").write_text(
            f"# Intent: {name or project.name}\n\n{intent}\n", encoding="utf-8")
        self._project = project
        self.push_screen(RunScreen())


def run_studio(project: Path | None, template: Path, *,
               sandbox_on: bool = True, mutation: bool = True,
               provider_name: str | None = None, model: str | None = None,
               name: str | None = None, intent: str | None = None) -> None:
    StudioApp(project, template, sandbox_on=sandbox_on, mutation=mutation,
              provider_name=provider_name, model=model, name=name, intent=intent).run()
