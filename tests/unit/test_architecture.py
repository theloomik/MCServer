"""Static guards for layer boundaries and the presentation conventions."""

import ast
import re
from pathlib import Path

import pytest

from mcserver.presentation.i18n import en

SOURCE = Path(__file__).resolve().parents[2] / "src" / "mcserver"
PRESENTATION = SOURCE / "presentation"


def imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


def python_files(directory: Path) -> list[Path]:
    return sorted(directory.rglob("*.py"))


@pytest.mark.parametrize("layer", ["domain", "application", "infrastructure", "bootstrap"])
def test_pyside6_is_imported_only_in_presentation(layer: str) -> None:
    offenders = [
        str(path.relative_to(SOURCE))
        for path in python_files(SOURCE / layer)
        if any(module.split(".")[0] == "PySide6" for module in imported_modules(path))
    ]

    assert offenders == []


def test_only_the_gui_composition_root_imports_bootstrap_or_infrastructure() -> None:
    offenders = [
        str(path.relative_to(SOURCE))
        for path in python_files(PRESENTATION)
        if path.name != "app.py"
        and any(
            module.startswith(("mcserver.bootstrap", "mcserver.infrastructure")) for module in imported_modules(path)
        )
    ]

    assert offenders == []


def test_message_catalog_and_paths_do_not_need_qt() -> None:
    for module in ("i18n/catalog.py", "i18n/en.py", "i18n/__init__.py", "paths.py", "services.py"):
        assert not any(name.startswith("PySide6") for name in imported_modules(PRESENTATION / module)), module


_INLINE_TEXT = re.compile(
    r"""(\.(setText|setWindowTitle|setToolTip|setStatusTip|setPlaceholderText|addMenu|addAction)\(\s*[rbf]?["'])"""
    r"""|(\bQ(Label|PushButton|CheckBox|RadioButton|GroupBox|Action|Menu)\(\s*[rbf]?["'])"""
)


@pytest.mark.parametrize(
    ("line", "flagged"),
    [
        ('label.setText("Hello")', True),
        ("self.setWindowTitle('MCServer')", True),
        ('menu.addAction("Exit")', True),
        ('QLabel("Servers")', True),
        ('label.setText(self._messages.text("app.title"))', False),
        ("QLabel(self._messages.text('main.placeholder'))", False),
        ("label.setToolTip(self._services.java_problem)", False),
    ],
)
def test_inline_text_pattern_detects_literals(line: str, flagged: bool) -> None:
    assert bool(_INLINE_TEXT.search(line)) is flagged


def test_presentation_has_no_inline_user_visible_strings() -> None:
    offenders = [
        f"{path.relative_to(SOURCE)}:{number}: {line.strip()}"
        for path in python_files(PRESENTATION)
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1)
        if _INLINE_TEXT.search(line)
    ]

    assert offenders == [], "Use Messages.text(key) instead of inline text"


_MESSAGE_KEY = re.compile(r"""\.(?:text|plural)\(\s*["']([a-z0-9_]+(?:\.[a-z0-9_]+)+)["']""")


def test_every_referenced_message_key_exists_in_english_catalog() -> None:
    referenced = {
        key
        for path in python_files(PRESENTATION)
        if "i18n" not in path.parts
        for key in _MESSAGE_KEY.findall(path.read_text(encoding="utf-8"))
    }

    assert referenced, "no message keys found; the scan pattern may be broken"
    assert sorted(referenced - set(en.MESSAGES)) == []
