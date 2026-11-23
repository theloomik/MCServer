"""Ukrainian catalog matches English, plural rules, language resolution and the language setting."""

from __future__ import annotations

import string
from collections.abc import Mapping
from pathlib import Path

import pytest
from pytestqt.qtbot import QtBot

from mcserver.presentation.i18n import en, messages_for, resolve_language, uk
from mcserver.presentation.i18n.catalog import ukrainian_plural

_FORMATTER = string.Formatter()


def placeholders(entry: str | Mapping[str, str]) -> set[str]:
    templates = [entry] if isinstance(entry, str) else list(entry.values())
    return {name for template in templates for _text, name, _spec, _conv in _FORMATTER.parse(template) if name}


def test_ukrainian_has_exactly_the_english_keys() -> None:
    assert set(uk.MESSAGES) == set(en.MESSAGES)


@pytest.mark.parametrize("key", sorted(en.MESSAGES))
def test_placeholders_match(key: str) -> None:
    english, ukrainian = en.MESSAGES[key], uk.MESSAGES[key]
    assert placeholders(ukrainian) <= placeholders(english) | {"count"}, key
    if isinstance(english, str):
        assert placeholders(ukrainian) == placeholders(english), key


def test_every_ukrainian_text_renders() -> None:
    messages = messages_for("uk")
    for key, entry in uk.MESSAGES.items():
        given = placeholders(entry) - ({"count"} if isinstance(entry, Mapping) else set())
        params = {name: 1 for name in given}
        rendered = messages.plural(key, 3, **params) if isinstance(entry, Mapping) else messages.text(key, **params)
        assert rendered and "{" not in rendered.replace("{}", ""), key


@pytest.mark.parametrize(
    ("count", "category"),
    [
        (1, "one"),
        (21, "one"),
        (101, "one"),
        (2, "few"),
        (4, "few"),
        (23, "few"),
        (5, "many"),
        (11, "many"),
        (12, "many"),
        (14, "many"),
        (0, "many"),
        (111, "many"),
        (112, "many"),
    ],
)
def test_ukrainian_plural_rule(count: int, category: str) -> None:
    assert ukrainian_plural(count) == category


def test_ukrainian_plural_forms_are_used() -> None:
    messages = messages_for("uk")
    assert messages.plural("properties.unsaved", 1) == "1 незбережена зміна"
    assert messages.plural("properties.unsaved", 3) == "3 незбережені зміни"
    assert messages.plural("properties.unsaved", 7) == "7 незбережених змін"


@pytest.mark.parametrize(
    ("setting", "system", "expected"),
    [
        (None, "uk_UA", "uk"),
        (None, "en_US", "en"),
        (None, "en-GB", "en"),
        (None, "de_DE", "uk"),
        (None, "", "uk"),
        ("en", "uk_UA", "en"),
        ("uk", "en_US", "uk"),
        ("fr", "en_US", "en"),
    ],
)
def test_language_resolution(setting: str | None, system: str, expected: str) -> None:
    assert resolve_language(setting, system) == expected


def test_settings_dialog_saves_the_language(qtbot: QtBot, tmp_path: Path) -> None:
    from test_m2_gui import Setup as M2Setup

    m2 = M2Setup(qtbot, tmp_path)
    m2.window.open_settings_dialog()
    dialog = m2.window.settings_dialog
    assert dialog is not None and dialog.language_combo.currentData() is None  # automatic by default
    dialog.language_combo.setCurrentIndex(dialog.language_combo.findData("uk"))
    dialog.save()
    assert m2.settings.current.language == "uk"
