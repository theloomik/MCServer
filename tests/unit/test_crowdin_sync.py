"""tools/crowdin_sync.py: config and locale checks, and the merge that protects translations."""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

import pytest

from tools import crowdin_sync as sync
from tools.crowdin_sync import SourceIndex, SyncError

SOURCE = {
    "app.title": "MCServer",
    "start.done": "{server_id} started.",
    "files_one": "{count} file",
    "files_other": "{count} files",
    "timer": "{minutes:02d}:{seconds:02d}",
}


def write(folder: Path, language: str, data: dict[str, str]) -> Path:
    path = folder / f"{language}.json"
    sync.write_locale(path, data)
    return path


# --- the repository's own files -------------------------------------------------------------


def test_repository_config_and_locales_pass_the_check() -> None:
    report = sync.check()
    assert report.errors == []


def test_crowdin_config_points_at_the_files_the_app_loads() -> None:
    assert sync.check_config(sync.CONFIG.read_text(encoding="utf-8")) == []
    source = sync.ROOT / "src/mcserver/presentation/i18n/locales/en.json"
    assert source.is_file()
    assert sync.target_languages() == ["uk"]


@pytest.mark.parametrize(
    ("text", "problem"),
    [
        ('"api_token": "abc"\n', "must not contain a project id or token"),
        ('"project_id": "123"\n', "must not contain a project id or token"),
    ],
)
def test_config_with_credentials_is_rejected(text: str, problem: str) -> None:
    config = sync.CONFIG.read_text(encoding="utf-8") + text
    assert any(problem in item for item in sync.check_config(config))


def test_config_pointing_elsewhere_is_rejected() -> None:
    config = sync.CONFIG.read_text(encoding="utf-8").replace("%two_letters_code%", "%locale%")
    assert any("translation must be" in item for item in sync.check_config(config))


def test_writing_keeps_the_existing_line_endings(tmp_path: Path) -> None:
    path = tmp_path / "uk.json"
    path.write_bytes(b'{\r\n  "a": "x"\r\n}\r\n')
    sync.write_locale(path, {"a": "x"})
    assert path.read_bytes() == b'{\r\n  "a": "x"\r\n}\r\n'


def test_locale_writing_keeps_unicode_and_the_repository_format(tmp_path: Path) -> None:
    path = write(tmp_path, "uk", {"a": "Сервер «survival» — запущено ✓"})
    raw = path.read_bytes()
    assert b"\r\n" not in raw and raw.endswith(b"}\n")
    assert "Сервер «survival» — запущено ✓" in raw.decode("utf-8")
    original = sync.ROOT / "src/mcserver/presentation/i18n/locales/uk.json"
    copy = tmp_path / "copy.json"
    sync.write_locale(copy, sync.read_locale(original))
    assert copy.read_text(encoding="utf-8") == original.read_text(encoding="utf-8").replace("\r\n", "\n")


# --- parsing and checking -------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ('{"a": "x", "a": "y"}', "duplicate key"),
        ('{"a": {"b": "x"}}', "must be a text"),
        ("[1, 2]", "JSON object"),
        ('{"a": "x",}', "not valid JSON"),
    ],
)
def test_bad_files_are_reported_clearly(text: str, message: str) -> None:
    with pytest.raises(SyncError, match=message):
        sync.parse_locale(text, "uk.json")


def test_check_reports_unknown_keys_broken_placeholders_and_untranslated() -> None:
    index = SourceIndex(SOURCE)
    report = sync.check_target(
        index,
        "uk",
        {
            "start.done": "{server} запущено.",  # renamed placeholder
            "files_one": "{count} файл",
            "files_few": "{count} файли",
            "files_many": "{count} файлів",
            "old.key": "застаріле",
            "timer": "{minutes:02d}:{seconds:02d}",
        },
    )
    assert any("'start.done'" in error and "placeholders" in error for error in report.errors)
    assert any("'old.key' is not an English key" in error for error in report.errors)
    assert not any("files_" in error or "timer" in error for error in report.errors)
    assert report.notes == ["uk.json: 1 untranslated (English is shown): app.title"]


def test_plural_forms_may_leave_out_count_but_not_invent_placeholders() -> None:
    index = SourceIndex(SOURCE)
    assert sync.placeholder_problem(index, "files_one", "один файл") is None
    assert sync.placeholder_problem(index, "files_few", "{count} файли {name}") is not None


# --- merge ----------------------------------------------------------------------------------


def test_merge_takes_new_translations_and_keeps_what_crowdin_did_not_deliver() -> None:
    previous = {"app.title": "MCServer", "start.done": "{server_id} запущено.", "files_one": "{count} файл"}
    downloaded = {"start.done": "Сервер {server_id} запущено.", "files_few": "{count} файли"}

    result = sync.merge_translations(SOURCE, downloaded, previous)

    assert result.data == {
        "app.title": "MCServer",
        "start.done": "Сервер {server_id} запущено.",
        "files_one": "{count} файл",
        "files_few": "{count} файли",
    }
    assert list(result.data) == ["app.title", "start.done", "files_one", "files_few"]  # English order
    assert result.from_crowdin == 2 and result.kept == 2


def test_merge_never_replaces_a_translation_with_english_or_a_broken_text() -> None:
    previous = {"start.done": "{server_id} запущено.", "timer": "{minutes:02d}:{seconds:02d}"}
    downloaded = {"start.done": "{server_id} started.", "timer": "{minutes}:{secs}"}

    result = sync.merge_translations(SOURCE, downloaded, previous)

    assert result.data == previous
    assert result.rejected == ["timer: placeholders ['minutes', 'secs'] differ from English ['minutes', 'seconds']"]


def test_merge_accepts_text_equal_to_english_when_nothing_better_exists() -> None:
    result = sync.merge_translations(SOURCE, {"app.title": "MCServer"}, {})
    assert result.data == {"app.title": "MCServer"}


def test_merge_drops_keys_english_no_longer_has_and_empty_texts() -> None:
    previous = {"gone.key": "старе", "start.done": "{server_id} запущено."}
    downloaded = {"gone.key": "старе", "start.done": "   "}

    result = sync.merge_translations(SOURCE, downloaded, previous)

    assert result.data == {"start.done": "{server_id} запущено."}
    assert result.dropped == ["gone.key"]


def test_merge_command_restores_a_file_crowdin_broke(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    write(tmp_path, "en", SOURCE)
    (tmp_path / "uk.json").write_text("{not json", encoding="utf-8")
    committed = {"start.done": "{server_id} запущено."}
    monkeypatch.setattr(sync, "previous_version", lambda _path, _ref: committed)

    lines = sync.merge("HEAD", tmp_path)

    assert "download unusable" in lines[0]
    assert sync.read_locale(tmp_path / "uk.json") == committed


def test_merge_reads_the_committed_file_from_git() -> None:
    if shutil.which("git") is None:
        pytest.skip("git is not available")
    path = sync.ROOT / "src/mcserver/presentation/i18n/locales/uk.json"
    committed = sync.previous_version(path, "HEAD")
    assert committed and all(isinstance(value, str) for value in committed.values())


# --- commands that talk to Crowdin ----------------------------------------------------------


def test_credentials_are_required_and_never_printed(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SyncError, match="CROWDIN_PERSONAL_TOKEN"):
        sync.require_credentials({"CROWDIN_PROJECT_ID": "123"})
    sync.require_credentials({"CROWDIN_PROJECT_ID": "123", "CROWDIN_PERSONAL_TOKEN": "secret-token-value"})
    assert "secret-token-value" not in capsys.readouterr().out


def test_download_without_credentials_fails_before_touching_files(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("CROWDIN_PROJECT_ID", raising=False)
    monkeypatch.delenv("CROWDIN_PERSONAL_TOKEN", raising=False)
    calls: list[tuple[str, ...]] = []
    monkeypatch.setattr(sync, "run_crowdin", lambda *args: calls.append(args))

    assert sync.main(["download"]) == 1
    assert calls == []
    assert "CROWDIN_PROJECT_ID" in capsys.readouterr().err


def test_download_refuses_uncommitted_locale_changes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CROWDIN_PROJECT_ID", "1")
    monkeypatch.setenv("CROWDIN_PERSONAL_TOKEN", "t")
    monkeypatch.setattr(sync, "locales_are_committed", lambda: False)
    calls: list[tuple[str, ...]] = []
    monkeypatch.setattr(sync, "run_crowdin", lambda *args: calls.append(args))
    assert sync.main(["download"]) == 1 and calls == []


def test_upload_runs_the_cli_after_a_clean_check(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CROWDIN_PROJECT_ID", "1")
    monkeypatch.setenv("CROWDIN_PERSONAL_TOKEN", "t")
    calls: list[tuple[str, ...]] = []
    monkeypatch.setattr(sync, "run_crowdin", lambda *args: calls.append(args))
    assert sync.main(["upload", "--translations"]) == 0
    assert calls == [("upload", "sources"), ("upload", "translations")]


def test_missing_cli_explains_how_to_install(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sync.shutil, "which", lambda _name: None)
    with pytest.raises(SyncError, match="Crowdin CLI was not found"):
        sync.crowdin_cli()


def test_workflow_keeps_secrets_out_of_the_repository() -> None:
    workflow = (sync.ROOT / ".github/workflows/crowdin.yml").read_text(encoding="utf-8")
    assert "${{ secrets.CROWDIN_PERSONAL_TOKEN }}" in workflow and "${{ secrets.CROWDIN_PROJECT_ID }}" in workflow
    assert "gh pr create --base dev" in workflow  # translations arrive as a pull request
    assert 'git push origin "$branch"' in workflow and "--force" not in workflow
    assert "python tools/crowdin_sync.py merge" in workflow
    for name in ("CROWDIN_PERSONAL_TOKEN", "CROWDIN_PROJECT_ID"):
        assert not os.environ.get(name) or os.environ[name] not in workflow


def test_downloaded_language_files_land_where_the_app_reads_them(tmp_path: Path) -> None:
    # Crowdin writes %two_letters_code%.json next to en.json; the app loads locales/<language>.json.
    config = sync.CONFIG.read_text(encoding="utf-8")
    translation = json.loads('"' + config.split('"translation": "')[1].split('"')[0] + '"')
    assert translation.replace("%two_letters_code%", "uk").lstrip("/") == f"{sync.LOCALES_DIR}/uk.json"
