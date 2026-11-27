"""Shared fake Minecraft server for integration tests (M1-QA-03).

The fake "Java" is a launcher (a ``.bat`` file on Windows, a shell script
elsewhere) that runs ``fake_server.py`` with the exact arguments the real
launch path builds: ``<java> -Xms..M -Xmx..M -jar <jar> nogui``. The script's
behaviour is read from the launched JAR file, so a test controls it through the
JAR it provisions. Behaviour is ``normal`` or whitespace-separated
``key=value`` options:

* ``ready_delay=<s>``  wait before printing the ``Done (…)!`` line
* ``never_ready=1``    never print it
* ``require_eula=1``   exit 1 with Minecraft's EULA message unless ``eula.txt`` says ``eula=true``
* ``stop_delay=<s>``   take this long to "save" after ``stop``
* ``ignore_stop=1``    ignore ``stop`` (only a kill ends it)
* ``crash_after=<s>``  exit on its own after this many seconds with ``exit_code``
* ``exit_code=<n>``    exit code for ``crash_after`` (default 1)
* ``crash_on_start=1`` exit 3 right away with an error line
* ``never_saves=1``    never confirm ``save-all flush`` (for backup timeout tests)

Every console line other than ``stop`` is echoed as ``echo: <line>``. The
first action is writing ``started.flag`` in the working directory, so a test
can tell whether the process ran at all.
"""

from __future__ import annotations

import os
import socket
import stat
import sys
from pathlib import Path

import pytest

from mcserver.application.errors import JavaNotFound
from mcserver.application.ports import JavaInstallation

FAKE_SERVER = r"""
import os
import sys
import threading
import time

with open("started.flag", "w", encoding="utf-8") as flag:
    flag.write(str(os.getpid()))

args = sys.argv[1:]
jar = args[args.index("-jar") + 1]
with open(jar, encoding="utf-8", errors="replace") as file:
    behaviour = file.read().strip()
options = dict(token.split("=", 1) for token in behaviour.split() if "=" in token)
print("cwd=" + os.getcwd(), flush=True)
print("args=" + "|".join(args), flush=True)
print("jar-content=" + behaviour, flush=True)
print("loading libraries", file=sys.stderr, flush=True)

if behaviour == "crash-on-start" or options.get("crash_on_start") == "1":
    print("Failed to start the minecraft server", file=sys.stderr, flush=True)
    sys.exit(3)

if options.get("require_eula") == "1":
    try:
        accepted = "eula=true" in open("eula.txt", encoding="utf-8").read().replace(" ", "").lower()
    except OSError:
        accepted = False
    if not accepted:
        print("[main/WARN]: You need to agree to the EULA in order to run the server.", flush=True)
        sys.exit(1)

if "crash_after" in options:
    def crash():
        time.sleep(float(options["crash_after"]))
        print("java.lang.OutOfMemoryError: Java heap space", file=sys.stderr, flush=True)
        os._exit(int(options.get("exit_code", "1")))
    threading.Thread(target=crash, daemon=True).start()

time.sleep(float(options.get("ready_delay", "0")))
if options.get("never_ready") != "1":
    print('[Server thread/INFO]: Done (0.1s)! For help, type "help"', flush=True)

for line in sys.stdin:
    command = line.strip()
    if command == "stop":
        if options.get("ignore_stop") == "1":
            print("ignoring stop", flush=True)
            continue
        print("Stopping the server", flush=True)
        time.sleep(float(options.get("stop_delay", "0")))
        print("Saved the world", flush=True)
        sys.exit(0)
    if command == "save-off":
        print("[Server thread/INFO]: Automatic saving is now disabled", flush=True)
    elif command == "save-all flush":
        if options.get("never_saves") != "1":
            print("[Server thread/INFO]: Saved the game", flush=True)
    elif command == "save-on":
        print("[Server thread/INFO]: Automatic saving is now enabled", flush=True)
    print("echo: " + command, flush=True)
"""


class FakeJavaResolver:
    """``JavaRuntimeProvider`` that always returns the controlled launcher (reported as Java 21)."""

    configured_executable = None

    def __init__(self, launcher: Path, major: int = 21) -> None:
        self._launcher = launcher
        self._major = major

    def find(self, minimum_major: int | None = None) -> JavaInstallation:
        if not self._launcher.name:
            raise JavaNotFound(minimum_major)
        return JavaInstallation(str(self._launcher), self._major, "path")

    def configure(self, executable: str | None) -> JavaInstallation | None:
        return None


def write_launcher(tools: Path) -> Path:
    """Write ``fake_server.py`` and a launcher for it into ``tools``; return the launcher."""
    tools.mkdir(parents=True, exist_ok=True)
    script = tools / "fake_server.py"
    script.write_text(FAKE_SERVER, encoding="utf-8")
    if os.name == "nt":
        launcher = tools / "java.bat"
        launcher.write_text(f'@"{sys.executable}" -u "{script}" %*\r\n', encoding="utf-8")
    else:
        launcher = tools / "java"
        launcher.write_text(f'#!/bin/sh\nexec "{sys.executable}" -u "{script}" "$@"\n', encoding="utf-8")
        launcher.chmod(launcher.stat().st_mode | stat.S_IXUSR)
    return launcher


@pytest.fixture
def fake_java(tmp_path: Path) -> Path:
    return write_launcher(tmp_path / "tools")


@pytest.fixture
def fake_server_script(fake_java: Path) -> Path:
    return fake_java.parent / "fake_server.py"


def use_free_port(server_folder: Path) -> int:
    """Give a test server its own free port, so tests never depend on 25565 being free on this machine."""
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = int(probe.getsockname()[1])
    server_folder.mkdir(parents=True, exist_ok=True)
    (server_folder / "server.properties").write_text(f"server-port={port}\n", encoding="utf-8")
    return port
