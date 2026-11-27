"""Catalog files for Crowdin: i18next JSON parsing, shipped files and the Crowdin configuration."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mcserver.presentation.i18n import en
from mcserver.presentation.i18n.catalog import load_catalog, parse_catalog

ROOT = Path(__file__).resolve().parents[3]
LOCALES = ROOT / "src" / "mcserver" / "presentation" / "i18n" / "locales"


def test_plural_suffixes_become_one_entry() -> None:
    catalog = parse_catalog({"a.title": "Title", "a.count_one": "{count} file", "a.count_other": "{count} files"})
    assert catalog == {"a.title": "Title", "a.count": {"one": "{count} file", "other": "{count} files"}}


def test_underscores_that_are_not_plural_forms_stay_part_of_the_key() -> None:
    assert parse_catalog({"server_list.title_count": "x"}) == {"server_list.title_count": "x"}


@pytest.mark.parametrize(
    ("data", "problem"),
    [({"a": 1}, "must be a string"), ({"a": "x", "a_one": "y"}, "both a plain text and a plural")],
)
def test_invalid_files_are_rejected(data: dict[str, object], problem: str) -> None:
    with pytest.raises(ValueError, match=problem):
        parse_catalog(data)


def test_files_are_flat_utf8_json_objects() -> None:
    for path in sorted(LOCALES.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        assert isinstance(data, dict) and all(isinstance(value, str) for value in data.values()), path.name


def test_packaged_english_matches_the_module() -> None:
    assert load_catalog("en") == dict(en.MESSAGES)


def test_crowdin_config_points_at_the_source_file() -> None:
    config = (ROOT / "crowdin.yml").read_text(encoding="utf-8")
    assert "/src/mcserver/presentation/i18n/locales/en.json" in config
    assert "%two_letters_code%.json" in config
    assert '"type": "i18next_json"' in config
    assert "api_token_env" in config and 'api_token"' not in config  # credentials never in the file
