"""The provider seam: discovery, the file-block protocol, and resolution.

The live provider calls (claude, the APIs) are exercised manually; here we cover
the deterministic surface that the rest of holdtrue depends on."""
import pathlib

import pytest

from holdtrue import providers


def test_registry_has_the_expected_shapes():
    names = {p.name for p in providers.all_providers()}
    assert {"claude", "anthropic-api", "openai-api", "ollama"} <= names
    kinds = {p.name: p.kind for p in providers.all_providers()}
    assert kinds["claude"] == providers.AGENT
    assert kinds["openai-api"] == providers.API


def test_parse_file_blocks_pulls_paths_and_bodies():
    text = (
        "preamble\n"
        "<<<FILE src/core.py>>>\n"
        "def f(x: int) -> int:\n    return x\n"
        "<<<ENDFILE>>>\n"
        "<<<FILE contract/manifest.yaml>>>\n"
        "version: 1\n"
        "<<<ENDFILE>>>\n"
    )
    blocks = dict(providers.parse_file_blocks(text))
    assert set(blocks) == {"src/core.py", "contract/manifest.yaml"}
    assert "return x" in blocks["src/core.py"]


def test_write_blocks_respects_allow_and_blocks_traversal(tmp_path: pathlib.Path):
    text = (
        "<<<FILE src/core.py>>>\nok\n<<<ENDFILE>>>\n"
        "<<<FILE ../escape.py>>>\nnope\n<<<ENDFILE>>>\n"
        "<<<FILE secret/keys.py>>>\nnope\n<<<ENDFILE>>>\n"
    )
    written = providers.write_blocks(text, tmp_path, allow=lambda r: r.startswith("src/"))
    assert written == ["src/core.py"]
    assert (tmp_path / "src" / "core.py").read_text() == "ok"
    assert not (tmp_path.parent / "escape.py").exists()
    assert not (tmp_path / "secret" / "keys.py").exists()


def test_resolve_unknown_raises():
    with pytest.raises(providers.ProviderError):
        providers.resolve("does-not-exist")


def test_studio_and_agents_import():
    from holdtrue import agents, studio
    assert callable(studio.run_studio)
    assert callable(agents.spawn_author)
    assert callable(agents.spawn_implementer)
