"""A live terminal dashboard for a holdtrue verification, built with Textual.

`holdtrue tui <project> --impl <file>` runs the contract against the implementation,
steps through the checks with a spinner, and lands the verdict. Select a check and
press enter to drill into its full detail. Pressing q while a run is in flight asks
to confirm, and aborts the running subprocesses.
"""
from __future__ import annotations

import threading
from pathlib import Path

from rich.text import Text
from textual.app import App, ComposeResult
from textual.screen import ModalScreen
from textual.widgets import DataTable, Footer, Static

from . import engine, sandbox, verify
from .classify import Classification, FAILED, GUARANTEED, UNGUARANTEED

# The turnstile logo and the wordmark, side by side (hardcoded: pyfiglet is not a
# runtime dependency). Matches the brand banner.
_LOGO = ["|   ", "|   ", "|-- ", "|   ", "|   "]
_WORDMARK = [
    ' _           _     _ _                   ',
    '| |__   ___ | | __| | |_ _ __ _   _  ___ ',
    "| '_ \\ / _ \\| |/ _` | __| '__| | | |/ _ \\",
    '| | | | (_) | | (_| | |_| |  | |_| |  __/',
    '|_| |_|\\___/|_|\\__,_|\\__|_|   \\__,_|\\___|',
]
_BANNER = "\n".join(f"{lo}  {wm}" for lo, wm in zip(_LOGO, _WORDMARK))

_SPINNER = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
_ICON = {"pass": "✓", "confirmed": "✓", "fail": "✗", "refuted": "✗",
         "unconfirmed": "~", "na": "·"}
_COLOR = {"pass": "#33ff66", "confirmed": "#33ff66", "fail": "#ff5f5f",
          "refuted": "#ff5f5f", "unconfirmed": "#f3c54e", "na": "#73897c"}
_LABEL = {"types": "types", "crosshair": "proof",
          "hypothesis_shown": "properties (shown)",
          "hypothesis_heldout": "properties (held-out)",
          "negative_probe": "negative-probe", "mutation": "mutation"}
_VERDICT_CLASS = {GUARANTEED: "ok", UNGUARANTEED: "warn", FAILED: "bad"}
_QUEUED = "#3a4a40"
_RUN = "#f3c54e"


class CheckDetail(ModalScreen):
    """Full detail for one check, overlaid on the dashboard."""

    BINDINGS = [("escape", "dismiss", "back"), ("q", "dismiss", "back")]
    CSS = """
    CheckDetail { align: center middle; }
    #detailbox { width: 84%; max-width: 96; height: auto; max-height: 80%;
                 border: round #2bbf57; background: #0c120c; padding: 1 2; }
    """

    def __init__(self, r: engine.CheckResult) -> None:
        super().__init__()
        self._r = r

    def compose(self) -> ComposeResult:
        r = self._r
        color = _COLOR.get(r.status, "#73897c")
        lines = [f"[b]{_LABEL.get(r.kind, r.kind)}[/b]  ([{color}]{r.status}[/])  "
                 f"[dim]{r.check_id}[/dim]", "", r.detail]
        if r.counterexample:
            lines += ["", f"[#ff5f5f]counterexample:[/] {r.counterexample}"]
        if r.extra:
            lines.append("")
            for k, val in r.extra.items():
                lines.append(f"  [dim]{k}:[/] {val}")
        lines += ["", "[dim]esc to go back[/dim]"]
        yield Static("\n".join(lines), id="detailbox")

    def action_dismiss(self) -> None:
        self.app.pop_screen()


class QuitConfirm(ModalScreen):
    """Confirm quitting while a run is still in flight."""

    BINDINGS = [("y", "confirm", "quit and abort"), ("n", "cancel", "stay"),
                ("escape", "cancel", "stay")]
    CSS = """
    QuitConfirm { align: center middle; }
    #quitbox { width: 58; height: auto; border: round #f3c54e; background: #0c120c;
               padding: 1 2; color: #cdddd2; }
    """

    def compose(self) -> ComposeResult:
        yield Static("a verification is still running.\n\nquit and abort it?   "
                     "[#33ff66]y[/] / [#7e9387]n[/]", id="quitbox")

    def action_confirm(self) -> None:
        self.app._quitting = True
        sandbox.abort_all()
        self.app.exit()

    def action_cancel(self) -> None:
        self.app.pop_screen()


class HoldtrueTUI(App):
    CSS = """
    Screen { background: #07090a; color: #cdddd2; }
    #logo { color: #33ff66; text-style: bold; padding: 1 2 0 2; }
    #meta { color: #2bbf57; padding: 1 2 0 2; }
    #summary { color: #7e9387; padding: 0 2 1 2; }
    #contract { color: #2bbf57; margin: 0 2 1 3; }
    DataTable { background: #07090a; margin: 0 2; height: auto; scrollbar-size: 0 0; }
    DataTable > .datatable--header { background: #07090a; color: #506054; text-style: none; }
    DataTable > .datatable--cursor { background: #14201a; }
    #hint { color: #506054; padding: 0 2; }
    #verdict { margin: 1 2; padding: 1 2; text-align: center; text-style: bold;
               border: heavy #18241d; color: #7e9387; }
    #verdict.ok { color: #33ff66; border: heavy #33ff66; }
    #verdict.warn { color: #f3c54e; border: heavy #f3c54e; }
    #verdict.bad { color: #ff5f5f; border: heavy #ff5f5f; }
    """
    BINDINGS = [("q", "request_quit", "quit")]

    def __init__(self, project: Path, impl: Path, manifest: dict,
                 sandbox_on: bool, mutation: bool) -> None:
        super().__init__()
        self._project = project
        self._impl = impl
        self._manifest = manifest
        self._sandbox_on = sandbox_on
        self._mutation = mutation
        self._order = ["types", "crosshair", "hypothesis_shown",
                       "hypothesis_heldout", "negative_probe"]
        if mutation:
            self._order.append("mutation")
        self._running = 0
        self._spin_i = 0
        self._done = False
        self._results: dict[str, engine.CheckResult] = {}
        self._quitting = False

    def compose(self) -> ComposeResult:
        m = self._manifest
        yield Static(_BANNER, id="logo")
        yield Static(f"{m.get('intent_id')}   impl={self._impl.name}", id="meta")
        yield Static(m.get("summary", ""), id="summary")
        decos = "\n".join(m.get("checks", {}).get("crosshair", {}).get("decorators", []))
        yield Static(f"{m.get('signature')}\n{decos}", id="contract")
        yield DataTable(id="checks", cursor_type="row", zebra_stripes=False)
        yield Static("up/down to move, enter to drill in, q to quit", id="hint")
        yield Static("verifying...", id="verdict")
        yield Footer()

    def on_mount(self) -> None:
        t = self.query_one("#checks", DataTable)
        t.add_column(" ", width=2, key="icon")
        t.add_column("check", width=22, key="check")
        t.add_column("status", width=12, key="status")
        t.add_column("detail", width=50, key="detail")
        for k in self._order:
            t.add_row(Text("·", style=_QUEUED), Text(_LABEL[k]),
                      Text("queued", style=_QUEUED), Text(""), key=k)
        t.focus()
        self.set_interval(0.09, self._spin)
        # A daemon thread (not a Textual worker): the interpreter kills it on exit,
        # so quitting never blocks on a running check. abort_all() kills the
        # subprocesses so nothing is orphaned.
        threading.Thread(target=self._run_verification, daemon=True).start()

    def action_request_quit(self) -> None:
        if self._done:
            self._quitting = True
            self.exit()
        else:
            self.push_screen(QuitConfirm())

    def _spin(self) -> None:
        if self._done or self._running >= len(self._order):
            return
        frame = _SPINNER[self._spin_i % len(_SPINNER)]
        self._spin_i += 1
        k = self._order[self._running]
        t = self.query_one("#checks", DataTable)
        t.update_cell(k, "icon", Text(frame, style=_RUN))
        t.update_cell(k, "status", Text("running", style=_RUN))

    def _run_verification(self) -> None:
        def safe(fn, *a) -> None:
            if self._quitting:
                return
            try:
                self.call_from_thread(fn, *a)
            except Exception:
                pass
        try:
            _, cls = verify.run_verification(
                self._project, self._impl, self._manifest,
                sandbox_on=self._sandbox_on, mutation=self._mutation,
                on_result=lambda r: safe(self._update, r))
        except Exception:
            return
        safe(self._finish, cls)

    def _update(self, r: engine.CheckResult) -> None:
        self._results[r.kind] = r
        t = self.query_one("#checks", DataTable)
        color = _COLOR.get(r.status, "#73897c")
        detail = r.detail if len(r.detail) <= 50 else r.detail[:49] + "…"
        t.update_cell(r.kind, "icon", Text(_ICON.get(r.status, "·"), style=color))
        t.update_cell(r.kind, "status", Text(r.status, style=color))
        t.update_cell(r.kind, "detail", Text(detail, style="#9fb3a6"))
        if r.kind in self._order:
            self._running = self._order.index(r.kind) + 1

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        r = self._results.get(event.row_key.value)
        if r is not None:
            self.push_screen(CheckDetail(r))

    def _finish(self, cls: Classification) -> None:
        self._done = True
        v = self.query_one("#verdict", Static)
        v.update(cls.classification)
        v.add_class(_VERDICT_CLASS.get(cls.classification, "muted"))
        v.styles.opacity = 0.0
        v.styles.animate("opacity", value=1.0, duration=0.5)


def run_dashboard(project: Path, impl: Path, manifest: dict, *,
                  sandbox_on: bool = True, mutation: bool = True) -> None:
    HoldtrueTUI(project, impl, manifest, sandbox_on, mutation).run()
