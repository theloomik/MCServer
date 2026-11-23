"""Key-based message lookup for user-visible text; independent of Qt."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable, Mapping
from importlib import resources

_logger = logging.getLogger(__name__)

Entry = str | Mapping[str, str]
"""A plain template, or plural templates keyed by category (``one``, ``few``, ``many``, ``other``)."""

Catalog = Mapping[str, Entry]
PluralRule = Callable[[int], str]

PLURAL_FORMS = ("zero", "one", "two", "few", "many", "other")
"""Key suffixes for plural forms in the JSON files (i18next style, as Crowdin writes them: ``key_one``)."""
LOCALES_PACKAGE = "mcserver.presentation.i18n"


def parse_catalog(data: Mapping[str, object], source: str = "catalog") -> dict[str, Entry]:
    """Turn a flat i18next-style mapping into a catalog: ``key_one``/``key_few``… become one plural entry."""
    catalog: dict[str, Entry] = {}
    plurals: dict[str, dict[str, str]] = {}
    for key, value in data.items():
        if not isinstance(value, str):
            raise ValueError(f"{source}: {key!r} must be a string")
        base, _, form = key.rpartition("_")
        if base and form in PLURAL_FORMS:
            plurals.setdefault(base, {})[form] = value
        else:
            catalog[key] = value
    for base, forms in plurals.items():
        if base in catalog:
            raise ValueError(f"{source}: {base!r} is both a plain text and a plural")
        catalog[base] = forms
    return catalog


def load_catalog(language: str) -> dict[str, Entry]:
    """Read ``locales/<language>.json`` shipped with the package (the files Crowdin syncs)."""
    path = resources.files(LOCALES_PACKAGE).joinpath("locales", f"{language}.json")
    return parse_catalog(json.loads(path.read_text(encoding="utf-8")), f"{language}.json")


def english_plural(count: int) -> str:
    """Return the English plural category for ``count``."""
    return "one" if count == 1 else "other"


def ukrainian_plural(count: int) -> str:
    """Return the Ukrainian (CLDR) plural category for the whole number ``count``: one, few or many."""
    tens, units = abs(count) % 100, abs(count) % 10
    if units == 1 and tens != 11:
        return "one"
    if 2 <= units <= 4 and not 12 <= tens <= 14:
        return "few"
    return "many"


class Messages:
    """Look up user-visible text by stable key, with named parameters and plurals.

    Templates use ``str.format`` named placeholders (``{server_id}``). A key
    missing from this catalog is looked up in ``fallback`` (English); a key
    missing everywhere is logged and rendered as the key itself so the GUI
    never crashes on a translation gap.
    """

    def __init__(
        self, catalog: Catalog, *, plural_rule: PluralRule = english_plural, fallback: Messages | None = None
    ) -> None:
        """Use ``catalog`` with its language's ``plural_rule`` and an optional ``fallback``."""
        self._catalog = catalog
        self._plural_rule = plural_rule
        self._fallback = fallback

    def has(self, key: str) -> bool:
        """Return whether ``key`` exists here or in the fallback."""
        return key in self._catalog or (self._fallback is not None and self._fallback.has(key))

    def text(self, key: str, **params: object) -> str:
        """Return the text for ``key`` with ``params`` filled in."""
        entry = self._catalog.get(key)
        if entry is None:
            return self._missing(key, lambda fallback: fallback.text(key, **params))
        template = entry if isinstance(entry, str) else entry.get("other", next(iter(entry.values()), key))
        return _format(key, template, params)

    def plural(self, key: str, count: int, **params: object) -> str:
        """Return the plural form of ``key`` for ``count``; ``{count}`` is always available."""
        entry = self._catalog.get(key)
        if entry is None:
            return self._missing(key, lambda fallback: fallback.plural(key, count, **params))
        values = {"count": count, **params}
        if isinstance(entry, str):
            return _format(key, entry, values)
        template = entry.get(self._plural_rule(count)) or entry.get("other") or key
        return _format(key, template, values)

    def _missing(self, key: str, from_fallback: Callable[[Messages], str]) -> str:
        if self._fallback is not None:
            return from_fallback(self._fallback)
        _logger.warning("Missing message key: %s", key)
        return key


def _format(key: str, template: str, params: Mapping[str, object]) -> str:
    """Fill a template, keeping the raw template if a placeholder has no value."""
    try:
        return template.format(**params)
    except (KeyError, IndexError, ValueError):
        _logger.warning("Could not format message %s with %s", key, sorted(params))
        return template
