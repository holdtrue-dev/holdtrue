"""Language plugin registry and plugin interface tests.

These tests do not run the full verification pipeline — they check that the
registry is correctly populated, the interface contract is met, and the
Python plugin's dispatch logic routes to the right path. End-to-end checks
for the Python paths are in test_loop.py / test_multi.py / test_pydantic.py.
"""
from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from holdtrue import languages
from holdtrue.languages.base import Language


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

def test_registry_not_empty() -> None:
    assert len(languages.names()) > 0


def test_registry_has_python() -> None:
    assert "python" in languages.names()


def test_registry_has_typescript() -> None:
    assert "typescript" in languages.names()


@pytest.mark.parametrize("name", ["rust", "go", "java", "csharp"])
def test_registry_has_new_languages(name: str) -> None:
    assert name in languages.names()


def test_get_returns_none_for_unknown() -> None:
    assert languages.get("cobol") is None


def test_all_languages_returns_list() -> None:
    all_langs = languages.all_languages()
    assert isinstance(all_langs, list)
    assert all(isinstance(lang, Language) for lang in all_langs)


# ---------------------------------------------------------------------------
# Interface contract: every plugin must satisfy the ABC
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("name", languages.names())
def test_plugin_has_required_attributes(name: str) -> None:
    lang = languages.get(name)
    assert lang is not None
    assert isinstance(lang.name, str) and lang.name
    assert isinstance(lang.display_name, str) and lang.display_name
    assert isinstance(lang.file_extension, str) and lang.file_extension.startswith(".")
    assert lang.verdict_ceiling in ("GUARANTEED", "ENFORCED")


@pytest.mark.parametrize("name", languages.names())
def test_plugin_available_returns_bool(name: str) -> None:
    lang = languages.get(name)
    assert lang is not None
    result = lang.available()
    assert isinstance(result, bool)


@pytest.mark.parametrize("name", languages.names())
def test_plugin_author_instructions_returns_str(name: str) -> None:
    lang = languages.get(name)
    assert lang is not None
    instructions = lang.author_instructions()
    assert isinstance(instructions, str)


@pytest.mark.parametrize("name", languages.names())
def test_plugin_run_checks_is_abstract_impl(name: str) -> None:
    lang = languages.get(name)
    assert lang is not None
    assert callable(lang.run_checks)


# ---------------------------------------------------------------------------
# Plugin-specific properties
# ---------------------------------------------------------------------------

def test_python_ceiling_is_guaranteed() -> None:
    lang = languages.get("python")
    assert lang is not None
    assert lang.verdict_ceiling == "GUARANTEED"


def test_python_is_always_available() -> None:
    lang = languages.get("python")
    assert lang is not None
    assert lang.available() is True


def test_typescript_ceiling_is_enforced() -> None:
    lang = languages.get("typescript")
    assert lang is not None
    assert lang.verdict_ceiling == "ENFORCED"


@pytest.mark.parametrize("name", ["rust", "go", "java", "csharp"])
def test_new_languages_have_enforced_or_guaranteed_ceiling(name: str) -> None:
    lang = languages.get(name)
    assert lang is not None
    assert lang.verdict_ceiling in ("GUARANTEED", "ENFORCED")


def test_rust_ceiling_is_guaranteed() -> None:
    lang = languages.get("rust")
    assert lang is not None
    # Rust can reach GUARANTEED via Kani (even if Kani is not installed here)
    assert lang.verdict_ceiling == "GUARANTEED"


@pytest.mark.parametrize("name", ["go", "java", "csharp"])
def test_interpreted_languages_cap_at_enforced(name: str) -> None:
    lang = languages.get(name)
    assert lang is not None
    assert lang.verdict_ceiling == "ENFORCED"


# ---------------------------------------------------------------------------
# Python plugin dispatch: routes single/multi/stateful without running checks
# ---------------------------------------------------------------------------

def test_python_plugin_is_correct_type() -> None:
    from holdtrue.languages.python_lang import PythonLanguage
    lang = languages.get("python")
    assert isinstance(lang, PythonLanguage)


def test_typescript_plugin_is_correct_type() -> None:
    from holdtrue.languages.typescript_lang import TypeScriptLanguage
    lang = languages.get("typescript")
    assert isinstance(lang, TypeScriptLanguage)


# ---------------------------------------------------------------------------
# verify.run_verification routes through the registry
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parents[1]


def test_verify_routes_python_single_function() -> None:
    """A manifest without a language: key routes to the Python plugin."""
    from holdtrue.verify import load_manifest, run_verification
    from holdtrue.classify import GUARANTEED

    project = ROOT / "examples" / "clamp"
    m = load_manifest(project, "contract/manifest.yaml")
    assert m.get("language") is None  # no explicit language = python default

    _, cls = run_verification(project, project / "controls" / "correct.py", m,
                              sandbox_on=False, mutation=False)
    assert cls.classification == GUARANTEED


def test_verify_routes_python_multi_function() -> None:
    """A multi-function manifest routes through the Python plugin's _run_multi."""
    from holdtrue.verify import load_manifest, run_verification
    from holdtrue.classify import GUARANTEED

    project = ROOT / "examples" / "dnd"
    m = load_manifest(project, "contract/manifest.yaml")
    assert "functions" in m

    _, cls = run_verification(project, project / "controls" / "correct.py", m,
                              sandbox_on=False, mutation=False)
    assert cls.classification == GUARANTEED


def test_verify_routes_typescript_by_language_key() -> None:
    """A manifest with language: typescript routes to the TypeScript plugin."""
    from holdtrue.verify import load_manifest, run_verification
    from holdtrue.classify import ENFORCED

    project = ROOT / "examples" / "ts-clamp"
    m = load_manifest(project, "contract/manifest.yaml")
    assert m.get("language") == "typescript"

    _, cls = run_verification(project, project / "controls" / "correct.ts", m,
                              sandbox_on=False, mutation=False)
    assert cls.classification == ENFORCED
