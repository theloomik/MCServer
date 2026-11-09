"""Message catalogs. Add a language by adding a module with ``MESSAGES`` and registering it below."""

from mcserver.presentation.i18n import en
from mcserver.presentation.i18n.catalog import Catalog, Messages, PluralRule, english_plural

DEFAULT_LANGUAGE = "en"

_LANGUAGES: dict[str, tuple[Catalog, PluralRule]] = {
    "en": (en.MESSAGES, english_plural),
}


def available_languages() -> tuple[str, ...]:
    """Return the language codes that have a catalog."""
    return tuple(_LANGUAGES)


def messages_for(language: str = DEFAULT_LANGUAGE) -> Messages:
    """Return messages for ``language``, falling back to English for unknown languages or keys."""
    english = Messages(en.MESSAGES, plural_rule=english_plural)
    if language == DEFAULT_LANGUAGE or language not in _LANGUAGES:
        return english
    catalog, plural_rule = _LANGUAGES[language]
    return Messages(catalog, plural_rule=plural_rule, fallback=english)


__all__ = ["DEFAULT_LANGUAGE", "Messages", "available_languages", "messages_for"]
