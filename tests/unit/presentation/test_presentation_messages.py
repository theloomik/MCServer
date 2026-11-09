"""Tests for key-based message lookup."""

import logging

import pytest

from mcserver.presentation.i18n import DEFAULT_LANGUAGE, available_languages, messages_for
from mcserver.presentation.i18n.catalog import Messages, english_plural


def ukrainian_like_plural(count: int) -> str:
    """Three-form rule used only to prove the mechanism supports Slavic plurals."""
    if count % 10 == 1 and count % 100 != 11:
        return "one"
    if count % 10 in (2, 3, 4) and count % 100 not in (12, 13, 14):
        return "few"
    return "many"


def test_text_fills_named_parameters() -> None:
    messages = Messages({"status.folder": "Servers folder: {path}"})

    assert messages.text("status.folder", path="C:/servers") == "Servers folder: C:/servers"


def test_english_plural_forms() -> None:
    messages = Messages({"lines": {"one": "{count} line skipped", "other": "{count} lines skipped"}})

    assert messages.plural("lines", 1) == "1 line skipped"
    assert messages.plural("lines", 0) == "0 lines skipped"
    assert messages.plural("lines", 5) == "5 lines skipped"


def test_three_form_plural_rule_is_supported() -> None:
    messages = Messages(
        {"lines": {"one": "{count} рядок", "few": "{count} рядки", "many": "{count} рядків"}},
        plural_rule=ukrainian_like_plural,
    )

    assert [messages.plural("lines", n) for n in (1, 3, 5, 11, 21, 22)] == [
        "1 рядок",
        "3 рядки",
        "5 рядків",
        "11 рядків",
        "21 рядок",
        "22 рядки",
    ]


def test_missing_key_falls_back_to_english() -> None:
    english = Messages({"app.title": "MCServer", "only.english": "Hello {name}"})
    other = Messages({"app.title": "МСервер"}, fallback=english)

    assert other.text("app.title") == "МСервер"
    assert other.text("only.english", name="Ann") == "Hello Ann"
    assert other.has("only.english")


def test_key_missing_everywhere_renders_key_and_logs(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING):
        assert Messages({}).text("does.not.exist") == "does.not.exist"
    assert "does.not.exist" in caplog.text


def test_missing_parameter_keeps_template_instead_of_crashing(caplog: pytest.LogCaptureFixture) -> None:
    messages = Messages({"status.folder": "Servers folder: {path}"})

    with caplog.at_level(logging.WARNING):
        assert messages.text("status.folder") == "Servers folder: {path}"


def test_plural_entry_used_as_text_returns_other_form() -> None:
    assert Messages({"lines": {"one": "a line", "other": "lines"}}).text("lines") == "lines"


def test_english_plural_rule() -> None:
    assert [english_plural(n) for n in (0, 1, 2)] == ["other", "one", "other"]


def test_english_is_default_and_unknown_language_falls_back() -> None:
    assert DEFAULT_LANGUAGE == "en"
    assert "en" in available_languages()
    assert messages_for().text("app.title") == "MCServer"
    assert messages_for("xx").text("app.title") == "MCServer"
