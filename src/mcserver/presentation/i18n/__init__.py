"""Message catalogs. Add a language by adding a module with ``MESSAGES`` and registering it below."""

from mcserver.presentation.i18n import en, uk
from mcserver.presentation.i18n.catalog import Catalog, Messages, PluralRule, english_plural, ukrainian_plural

DEFAULT_LANGUAGE = "en"
FALLBACK_SYSTEM_LANGUAGE = "uk"
"""Used when Windows is set to a language MCServer has no catalog for (product decision)."""

_LANGUAGES: dict[str, tuple[Catalog, PluralRule]] = {
    "en": (en.MESSAGES, english_plural),
    "uk": (uk.MESSAGES, ukrainian_plural),
}


def available_languages() -> tuple[str, ...]:
    """Return the language codes that have a catalog."""
    return tuple(_LANGUAGES)


def resolve_language(setting: str | None, system_locale: str) -> str:
    """Return the language to show: the user's setting, else the Windows UI language when known, else Ukrainian.

    ``system_locale`` is a name such as ``uk_UA`` or ``en_US`` (``QLocale.system().name()``).
    """
    if setting in _LANGUAGES:
        return str(setting)
    system = system_locale.replace("-", "_").split("_")[0].lower()
    return system if system in _LANGUAGES else FALLBACK_SYSTEM_LANGUAGE


def messages_for(language: str = DEFAULT_LANGUAGE) -> Messages:
    """Return messages for ``language``, falling back to English for unknown languages or keys."""
    english = Messages(en.MESSAGES, plural_rule=english_plural)
    if language == DEFAULT_LANGUAGE or language not in _LANGUAGES:
        return english
    catalog, plural_rule = _LANGUAGES[language]
    return Messages(catalog, plural_rule=plural_rule, fallback=english, language=language)


__all__ = ["DEFAULT_LANGUAGE", "Messages", "available_languages", "messages_for", "resolve_language"]
