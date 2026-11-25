"""Synchronise MCServer's translations with Crowdin without losing translations (see docs/translations.md).

English (``en.json``) is the source and is edited in the repository. Crowdin
holds the other languages. Commands:

``check``
    Validate ``crowdin.yml`` and every locale file: flat UTF-8 JSON, no
    duplicate or unknown keys, placeholders exactly as in English, plural
    forms of known keys. Reports untranslated keys. Exit code 1 on errors.
``merge [--base REF]``
    Run after ``crowdin download``. For every translation file it keeps what
    Crowdin delivered, unless that would lose something: a key Crowdin did not
    deliver keeps the repository's translation from ``REF`` (default HEAD); a
    delivered text that is just the English source, or that breaks
    placeholders, keeps the repository's translation too. Keys English no
    longer has are dropped. Files are written in English key order.
``upload [--translations]``
    ``check``, then ``crowdin upload sources`` (and, with ``--translations``,
    ``crowdin upload translations`` to seed Crowdin with the repository's
    translations).
``download``
    Refuse when the locale files have uncommitted changes, then
    ``crowdin download``, ``merge`` and ``check``.

``upload`` and ``download`` need the Crowdin CLI and the environment
variables ``CROWDIN_PROJECT_ID`` and ``CROWDIN_PERSONAL_TOKEN``; their values
are never printed.

Only the standard library is used, so CI can run this without the app's
dependencies.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import string
import subprocess  # nosec B404 - runs git and the Crowdin CLI with fixed argument lists
import sys
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "crowdin.yml"
LOCALES_DIR = "src/mcserver/presentation/i18n/locales"
LOCALES = ROOT / LOCALES_DIR
SOURCE_LANGUAGE = "en"
PLURAL_FORMS = ("zero", "one", "two", "few", "many", "other")
"""Suffixes of plural keys (i18next JSON, as Crowdin writes them); the same list the app uses."""
ENV_PROJECT = "CROWDIN_PROJECT_ID"
ENV_TOKEN = "CROWDIN_PERSONAL_TOKEN"  # nosec B105 - the name of an environment variable, not a secret


class SyncError(Exception):
    """A problem the user must fix; the message says how."""


# --- reading and writing locale files ---------------------------------------------------------


def _no_duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise SyncError(f"duplicate key {key!r}")
        result[key] = value
    return result


def parse_locale(text: str, name: str) -> dict[str, str]:
    """Return the flat ``key: text`` mapping of a locale file; raise ``SyncError`` for anything else."""
    try:
        data = json.loads(text, object_pairs_hook=_no_duplicates)
    except SyncError as error:
        raise SyncError(f"{name}: {error}") from None
    except json.JSONDecodeError as error:
        raise SyncError(f"{name}: not valid JSON ({error})") from None
    if not isinstance(data, dict):
        raise SyncError(f"{name}: must be a JSON object of key/text pairs")
    for key, value in data.items():
        if not isinstance(value, str):
            raise SyncError(f"{name}: {key!r} must be a text, not {type(value).__name__} (files must stay flat)")
    return data


def read_locale(path: Path) -> dict[str, str]:
    """Read one locale file."""
    return parse_locale(path.read_text(encoding="utf-8"), path.name)


def write_locale(path: Path, data: Mapping[str, str]) -> None:
    """Write ``data`` as the repository formats locale files: UTF-8, two-space indent, final newline.

    Line endings stay as the existing file has them (CRLF in a Windows checkout, LF otherwise), so a
    merge that changes no text leaves the file unchanged for git.
    """
    newline = "\r\n" if path.is_file() and b"\r\n" in path.read_bytes() else "\n"
    text = json.dumps(dict(data), ensure_ascii=False, indent=2) + "\n"
    with path.open("w", encoding="utf-8", newline=newline) as handle:
        handle.write(text)


def target_languages(locales: Path = LOCALES) -> list[str]:
    """Return the translation languages that have a file (every ``xx.json`` except English)."""
    return sorted(path.stem for path in locales.glob("*.json") if path.stem != SOURCE_LANGUAGE)


# --- keys and placeholders --------------------------------------------------------------------


def split_key(key: str) -> tuple[str, str | None]:
    """Return ``(base, plural form)``; the form is ``None`` for a plain key."""
    base, _, form = key.rpartition("_")
    if base and form in PLURAL_FORMS:
        return base, form
    return key, None


def placeholders(text: str) -> set[str]:
    """Return the names used in ``{name}`` placeholders (``{{`` and ``}}`` are literal braces)."""
    try:
        return {name.split(".")[0].split("[")[0] for _, name, _, _ in string.Formatter().parse(text) if name}
    except ValueError:
        return {"<unbalanced braces>"}


@dataclass
class SourceIndex:
    """The English keys, grouped so plural forms of other languages can be matched to them."""

    source: dict[str, str]
    plain: dict[str, str] = field(default_factory=dict)
    plurals: dict[str, dict[str, str]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for key, value in self.source.items():
            base, form = split_key(key)
            if form is None:
                self.plain[key] = value
            else:
                self.plurals.setdefault(base, {})[form] = value

    def expected_placeholders(self, key: str) -> set[str] | None:
        """Return the placeholders ``key`` must use, or ``None`` when English has no such key."""
        if key in self.plain:
            return placeholders(self.plain[key])
        base, form = split_key(key)
        if form is not None and base in self.plurals:
            found: set[str] = set()
            for text in self.plurals[base].values():
                found |= placeholders(text)
            return found
        return None

    def is_plural(self, key: str) -> bool:
        base, form = split_key(key)
        return form is not None and base in self.plurals

    def english_text(self, key: str) -> str | None:
        """Return the English text a translation of ``key`` corresponds to."""
        if key in self.plain:
            return self.plain[key]
        base, form = split_key(key)
        forms = self.plurals.get(base)
        if form is None or forms is None:
            return None
        return forms.get(form) or forms.get("other")

    def bases(self) -> list[str]:
        """Return every English text id (plain keys, plural bases) in file order."""
        seen: list[str] = []
        for key in self.source:
            base, form = split_key(key)
            entry = key if form is None else base
            if entry not in seen:
                seen.append(entry)
        return seen


def placeholder_problem(index: SourceIndex, key: str, text: str) -> str | None:
    """Return why ``text`` cannot be used for ``key``, or ``None`` when its placeholders are right."""
    expected = index.expected_placeholders(key)
    if expected is None:
        return "English has no such key"
    used = placeholders(text)
    if index.is_plural(key):
        # A plural form may leave out {count} ("one file"), but must not invent placeholders.
        extra = used - expected - {"count"}
        return f"unknown placeholders {sorted(extra)}" if extra else None
    if used != expected:
        return f"placeholders {sorted(used)} differ from English {sorted(expected)}"
    return None


# --- check ------------------------------------------------------------------------------------


@dataclass
class Report:
    """Problems found by ``check``: errors fail it, notes are information."""

    errors: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def check_config(text: str) -> list[str]:
    """Return problems in ``crowdin.yml``'s text (it must point at the files MCServer loads)."""
    problems: list[str] = []
    values = dict(re.findall(r'^\s*-?\s*"([a-z_]+)"\s*:\s*"([^"]*)"', text, flags=re.MULTILINE))
    if values.get("project_id_env") != ENV_PROJECT or values.get("api_token_env") != ENV_TOKEN:
        problems.append(f"crowdin.yml must read the project and token from {ENV_PROJECT} and {ENV_TOKEN}")
    if re.search(r'^\s*"?(api_token|project_id)"?\s*:', text, flags=re.MULTILINE):
        problems.append("crowdin.yml must not contain a project id or token; use the *_env settings")
    if values.get("source") != f"/{LOCALES_DIR}/{SOURCE_LANGUAGE}.json":
        problems.append(f"crowdin.yml: source must be /{LOCALES_DIR}/{SOURCE_LANGUAGE}.json")
    if values.get("translation") != f"/{LOCALES_DIR}/%two_letters_code%.json":
        problems.append(f"crowdin.yml: translation must be /{LOCALES_DIR}/%two_letters_code%.json")
    if values.get("type") != "i18next_json":
        problems.append("crowdin.yml: type must be i18next_json")
    return problems


def check_target(index: SourceIndex, language: str, data: Mapping[str, str]) -> Report:
    """Check one translation file against English."""
    report = Report()
    name = f"{language}.json"
    for key, text in data.items():
        problem = placeholder_problem(index, key, text)
        if problem == "English has no such key":
            report.errors.append(f"{name}: {key!r} is not an English key (remove it or add it to en.json)")
        elif problem is not None:
            report.errors.append(f"{name}: {key!r}: {problem}")
        if not text.strip():
            report.errors.append(f"{name}: {key!r} is empty (leave the key out to fall back to English)")
    translated = {split_key(key)[0] if index.is_plural(key) else key for key in data}
    missing = [base for base in index.bases() if base not in translated]
    if missing:
        shown = ", ".join(missing[:5]) + (" …" if len(missing) > 5 else "")
        report.notes.append(f"{name}: {len(missing)} untranslated (English is shown): {shown}")
    return report


def check(locales: Path = LOCALES, config: Path = CONFIG) -> Report:
    """Check ``crowdin.yml`` and every locale file."""
    report = Report(errors=check_config(config.read_text(encoding="utf-8")))
    try:
        source = read_locale(locales / f"{SOURCE_LANGUAGE}.json")
    except (OSError, SyncError) as error:
        report.errors.append(str(error))
        return report
    index = SourceIndex(source)
    for key, text in source.items():
        if "<unbalanced braces>" in placeholders(text):
            report.errors.append(f"en.json: {key!r} has unbalanced braces")
    for language in target_languages(locales):
        try:
            data = read_locale(locales / f"{language}.json")
        except (OSError, SyncError) as error:
            report.errors.append(str(error))
            continue
        result = check_target(index, language, data)
        report.errors += result.errors
        report.notes += result.notes
    return report


# --- merge ------------------------------------------------------------------------------------


@dataclass
class MergeResult:
    """What ``merge`` did with one file."""

    data: dict[str, str]
    from_crowdin: int = 0
    kept: int = 0
    rejected: list[str] = field(default_factory=list)
    dropped: list[str] = field(default_factory=list)


def _ordered_keys(index: SourceIndex, candidates: Iterable[str]) -> list[str]:
    wanted = set(candidates)
    ordered: list[str] = []
    for base in index.bases():
        if base in index.plain:
            if base in wanted:
                ordered.append(base)
            continue
        ordered += [f"{base}_{form}" for form in PLURAL_FORMS if f"{base}_{form}" in wanted]
    return ordered


def merge_translations(
    source: Mapping[str, str], downloaded: Mapping[str, str], previous: Mapping[str, str]
) -> MergeResult:
    """Combine Crowdin's file with the repository's, never trading a translation for English or a broken text."""
    index = SourceIndex(dict(source))
    result = MergeResult(data={})
    known = [key for key in {**previous, **downloaded} if index.expected_placeholders(key) is not None]
    result.dropped = sorted(key for key in {**previous, **downloaded} if key not in known)
    for key in _ordered_keys(index, known):
        new, old = downloaded.get(key), previous.get(key)
        if new is not None and new.strip():
            problem = placeholder_problem(index, key, new)
            echoes_english = new == index.english_text(key) and old is not None and old != new
            if problem is None and not echoes_english:
                result.data[key] = new
                result.from_crowdin += new != old
                continue
            if problem is not None:
                result.rejected.append(f"{key}: {problem}")
        if old is not None and placeholder_problem(index, key, old) is None:
            result.data[key] = old
            result.kept += new is None or new != old
    return result


def _git(*args: str) -> subprocess.CompletedProcess[str]:
    git = shutil.which("git")
    if git is None:
        raise SyncError("git was not found on PATH")
    return subprocess.run([git, *args], cwd=ROOT, capture_output=True, text=True, encoding="utf-8", check=False)  # nosec B603


def previous_version(path: Path, ref: str) -> dict[str, str]:
    """Return ``path`` as committed at ``ref`` (empty when it did not exist there)."""
    relative = path.relative_to(ROOT).as_posix()
    shown = _git("show", f"{ref}:{relative}")
    if shown.returncode != 0:
        return {}
    return parse_locale(shown.stdout, f"{path.name}@{ref}")


def merge(ref: str = "HEAD", locales: Path = LOCALES) -> list[str]:
    """Merge every downloaded translation file with its version at ``ref``; return a summary per file."""
    source = read_locale(locales / f"{SOURCE_LANGUAGE}.json")
    lines: list[str] = []
    for language in target_languages(locales):
        path = locales / f"{language}.json"
        previous = previous_version(path, ref)
        try:
            downloaded = read_locale(path)
        except SyncError as error:
            # Crowdin wrote something unusable: keep the committed file.
            write_locale(path, previous)
            lines.append(f"{path.name}: download unusable ({error}); the committed file was kept")
            continue
        result = merge_translations(source, downloaded, previous)
        write_locale(path, result.data)
        lines.append(
            f"{path.name}: {result.from_crowdin} updated from Crowdin, {result.kept} kept from the repository, "
            f"{len(result.rejected)} rejected, {len(result.dropped)} obsolete keys dropped"
        )
        lines += [f"  rejected {item}" for item in result.rejected]
    return lines


# --- Crowdin CLI ------------------------------------------------------------------------------


def require_credentials(environ: Mapping[str, str] = os.environ) -> None:
    """Raise when the project id or token is missing (their values are never shown)."""
    missing = [name for name in (ENV_PROJECT, ENV_TOKEN) if not environ.get(name, "").strip()]
    if missing:
        raise SyncError(
            "Set " + " and ".join(missing) + " in the environment (see docs/translations.md); "
            "never put them in crowdin.yml or commit them."
        )


def crowdin_cli() -> str:
    """Return the Crowdin CLI executable."""
    found = shutil.which("crowdin")
    if found is None:
        raise SyncError(
            "The Crowdin CLI was not found. Install it (https://crowdin.github.io/crowdin-cli/installation), "
            "for example with 'npm install -g @crowdin/cli', and open a new terminal."
        )
    return found


def run_crowdin(*args: str) -> None:
    """Run the Crowdin CLI in the repository root; raise with its exit code on failure."""
    completed = subprocess.run([crowdin_cli(), *args, "--config", str(CONFIG)], cwd=ROOT, check=False)  # nosec B603
    if completed.returncode != 0:
        raise SyncError(
            f"'crowdin {' '.join(args)}' failed (exit code {completed.returncode}). "
            "Common causes: a wrong project id, an expired token or one without project access, no network."
        )


def locales_are_committed() -> bool:
    """Return whether the locale files have no uncommitted changes."""
    status = _git("status", "--porcelain", "--", LOCALES_DIR)
    return status.returncode == 0 and not status.stdout.strip()


# --- command line -----------------------------------------------------------------------------


def _print_report(report: Report) -> int:
    for note in report.notes:
        print(f"note: {note}")
    for error in report.errors:
        print(f"error: {error}", file=sys.stderr)
    if report.errors:
        print(f"{len(report.errors)} problem(s) found.", file=sys.stderr)
        return 1
    print("Translations are consistent.")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Run one command; return the exit code."""
    parser = argparse.ArgumentParser(prog="crowdin_sync", description=__doc__.split("\n\n")[0])
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("check", help="validate crowdin.yml and the locale files")
    merge_parser = commands.add_parser("merge", help="merge downloaded files with the committed ones")
    merge_parser.add_argument("--base", default="HEAD", help="git revision of the files before the download")
    upload_parser = commands.add_parser("upload", help="upload en.json (and optionally translations)")
    upload_parser.add_argument("--translations", action="store_true", help="also upload the repository's translations")
    commands.add_parser("download", help="download, merge and check translations")
    args = parser.parse_args(argv)
    try:
        if args.command == "check":
            return _print_report(check())
        if args.command == "merge":
            for line in merge(args.base):
                print(line)
            return _print_report(check())
        if args.command == "upload":
            if _print_report(check()):
                raise SyncError("Fix the problems above before uploading.")
            require_credentials()
            run_crowdin("upload", "sources")
            if args.translations:
                run_crowdin("upload", "translations")
            return 0
        require_credentials()
        if not locales_are_committed():
            raise SyncError(f"{LOCALES_DIR} has uncommitted changes; commit or stash them before downloading.")
        run_crowdin("download")
        for line in merge("HEAD"):
            print(line)
        return _print_report(check())
    except SyncError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
