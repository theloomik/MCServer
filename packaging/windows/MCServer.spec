# PyInstaller spec for MCServer 2.0 (M5). Run through tools/build_windows.py, which draws the icon and
# writes the version resource first and passes them in MCSERVER_ICON and MCSERVER_VERSION_FILE.
#
# One folder, not one file: the app starts without unpacking itself to %TEMP% each time, and the
# installer updates it in place. User data never goes here: a packaged MCServer keeps servers and
# settings in %LOCALAPPDATA%\MCServer\servers (mcserver.presentation.paths).
# ruff: noqa
import os
from pathlib import Path

ROOT = Path(SPECPATH).resolve().parents[1]
SOURCE = ROOT / "src"
ICON = os.environ.get("MCSERVER_ICON")
VERSION_FILE = os.environ.get("MCSERVER_VERSION_FILE")
if not ICON or not VERSION_FILE:
    raise SystemExit("Build with: .venv\\Scripts\\python tools\\build_windows.py")

a = Analysis(
    [str(SOURCE / "mcserver" / "presentation" / "__main__.py")],
    pathex=[str(SOURCE)],
    datas=[
        # Read with importlib.resources (mcserver.presentation.i18n.catalog).
        (str(SOURCE / "mcserver" / "presentation" / "i18n" / "locales"), "mcserver/presentation/i18n/locales"),
        (str(ROOT / "LICENSE"), "."),
    ],
    # Not used by MCServer; kept out to save space.
    excludes=["tkinter", "unittest", "pydoc", "doctest", "lib2to3", "pytest", "PySide6.QtNetwork", "PySide6.QtQml",
              "PySide6.QtQuick", "PySide6.QtOpenGL", "PySide6.QtPdf", "PySide6.QtWebEngineCore"],
    noarchive=False,
)

# Qt plugins pull in libraries a widgets app never loads (Qt Quick/QML through the virtual keyboard,
# Qt PDF through the PDF image plugin, software OpenGL). MCServer draws with QtWidgets and QtSvg, shows
# PNG/SVG/ICO images and has its own translations, so these are left out (about 50 MB).
UNUSED = (
    "opengl32sw.dll", "Qt6Quick", "Qt6Qml", "Qt6Pdf", "Qt6OpenGL", "Qt6VirtualKeyboard", "Qt6Network",
    "platforminputcontexts/", "platforms/qdirect2d", "platforms/qminimal", "platforms/qoffscreen",
    "imageformats/qtiff", "imageformats/qwebp", "imageformats/qjpeg", "imageformats/qpdf",
    "imageformats/qicns", "imageformats/qtga", "imageformats/qwbmp", "PySide6/translations/",
)


def _needed(entry):
    name = entry[0].replace("\\", "/")
    return not any(part in name for part in UNUSED)


a.binaries = [entry for entry in a.binaries if _needed(entry)]
a.datas = [entry for entry in a.datas if _needed(entry)]
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="MCServer",
    console=False,  # a window application: no console behind it
    icon=ICON,
    version=VERSION_FILE,
    upx=False,  # UPX-packed files start slower and are flagged by antivirus software more often
)

coll = COLLECT(exe, a.binaries, a.datas, name="MCServer", upx=False)
