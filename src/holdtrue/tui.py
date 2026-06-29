"""A live terminal dashboard for a holdtrue verification, built with Textual.

`holdtrue tui <project> --impl <file>` runs the contract against the implementation
and streams each check as it lands, then shows the verdict.
"""
from __future__ import annotations

from pathlib import Path

from textual import work
from textual.app import App, ComposeResult
from textual.containers import VerticalScroll
from textual.widgets import Footer, Static

from . import engine, verify
from .classify import Classification, FAILED, GUARANTEED, UNGUARANTEED

_COLOR = {
    "pass": "#33ff66", "confirmed": "#33ff66",
    "fail": "#ff5f5f", "refuted": "#ff5f5f",
    "unconfirmed": "#f3c54e", "na": "#73897c",
}
_VERDICT_CLASS = {GUARANTEED: "ok", UNGUARANTEED: "warn", FAILED: "bad"}


class HoldtrueTUI(App):
    CSS = """
    Screen { background: #07090a; color: #cdddd2; }
    #title { color: #33ff66; text-style: bold; padding: 1 2 0 2; }
    #summary { color: #7e9387; padding: 0 2 1 2; }
    #contract { color: #2bbf57; border: round #18241d; margin: 0 2 1 2; padding: 0 1; }
    #checks { margin: 0 2; height: 1fr; }
    .row { height: auto; }
    #verdict { margin: 1 2; padding: 1 2; text-align: center; text-style: bold;
               border: heavy #18241d; color: #7e9387; }
    #verdict.ok { color: #33ff66; border: heavy #33ff66; }
    #verdict.warn { color: #f3c54e; border: heavy #f3c54e; }
    #verdict.bad { color: #ff5f5f; border: heavy #ff5f5f; }
    """
    BINDINGS = [("q", "quit", "quit")]

    def __init__(self, project: Path, impl: Path, manifest: dict,
                 sandbox_on: bool, mutation: bool) -> None:
        super().__init__()
        self._project = project
        self._impl = impl
        self._manifest = manifest
        self._sandbox_on = sandbox_on
        self._mutation = mutation

    def compose(self) -> ComposeResult:
        m = self._manifest
        yield Static(f"holdtrue   {m.get('intent_id')}   impl={self._impl.name}", id="title")
        yield Static(m.get("summary", ""), id="summary")
        decos = "\n".join(m.get("checks", {}).get("crosshair", {}).get("decorators", []))
        yield Static(f"{m.get('signature')}\n{decos}", id="contract")
        yield VerticalScroll(id="checks")
        yield Static("running...", id="verdict")
        yield Footer()

    def on_mount(self) -> None:
        self._run()

    @work(thread=True)
    def _run(self) -> None:
        def on_result(r: engine.CheckResult) -> None:
            self.call_from_thread(self._add_check, r)
        _, cls = verify.run_verification(
            self._project, self._impl, self._manifest,
            sandbox_on=self._sandbox_on, mutation=self._mutation, on_result=on_result)
        self.call_from_thread(self._show_verdict, cls)

    def _add_check(self, r: engine.CheckResult) -> None:
        color = _COLOR.get(r.status, "#73897c")
        text = f"{r.kind:<16} [{color}]{r.status:<10}[/]  {r.detail[:46]}"
        self.query_one("#checks").mount(Static(text, classes="row"))

    def _show_verdict(self, cls: Classification) -> None:
        v = self.query_one("#verdict", Static)
        v.update(cls.classification)
        v.add_class(_VERDICT_CLASS.get(cls.classification, "muted"))


def run_dashboard(project: Path, impl: Path, manifest: dict, *,
                  sandbox_on: bool = True, mutation: bool = True) -> None:
    HoldtrueTUI(project, impl, manifest, sandbox_on, mutation).run()
