"""Language plugin registry."""
from __future__ import annotations

from .base import Language

_registry: dict[str, Language] = {}


def register(lang: Language) -> None:
    _registry[lang.name] = lang


def get(name: str) -> Language | None:
    return _registry.get(name)


def all_languages() -> list[Language]:
    return list(_registry.values())


def names() -> list[str]:
    return list(_registry.keys())


def _bootstrap() -> None:
    from .python_lang import PythonLanguage
    from .typescript_lang import TypeScriptLanguage
    from .rust_lang import RustLanguage
    from .go_lang import GoLanguage
    from .java_lang import JavaLanguage
    from .csharp_lang import CSharpLanguage

    for lang in [PythonLanguage(), TypeScriptLanguage(), RustLanguage(),
                 GoLanguage(), JavaLanguage(), CSharpLanguage()]:
        register(lang)


_bootstrap()
