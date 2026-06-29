"""The TUI module imports and exposes its entrypoints (guards against regressions;
the live rendering is exercised manually)."""


def test_tui_imports():
    from holdtrue import tui

    assert tui.HoldtrueTUI is not None
    assert callable(tui.run_dashboard)
