import json
import subprocess
import sys

import core


def make_manager(tmp_path):
    return core.ServerManager(str(tmp_path / "servers"))


def test_create_rename_delete_server(tmp_path):
    manager = make_manager(tmp_path)
    jar = tmp_path / "paper.jar"
    jar.write_bytes(b"jar")

    assert manager.create_server("Survival", str(jar), 2048)
    assert manager.rename_server("Survival", "Creative")
    assert manager.delete_server("Creative")
    assert json.loads(manager.config_file.read_text(encoding="utf-8")) == {}
    manager.cleanup()


def test_manager_never_deletes_external_directory(tmp_path):
    manager = make_manager(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    server = core.ServerData("Outside", "paper.jar", str(outside / "paper.jar"), 1024, str(outside))
    manager.servers["Outside"] = server

    assert not manager.delete_server("Outside")
    assert outside.exists()
    manager.cleanup()


def test_server_start_rejects_busy_port(tmp_path, monkeypatch):
    server_dir = tmp_path / "server"
    server_dir.mkdir()
    (server_dir / "server.properties").write_text("server-ip=127.0.0.1\nserver-port=25565\n", encoding="utf-8")
    logs = []
    stopped = []
    callbacks = core.ServerCallbacks(lambda text, level: logs.append((text, level)), lambda *_: None, lambda *_: None, stopped.append)
    instance = core.ServerInstance(
        core.ServerData("Test", "paper.jar", str(server_dir / "paper.jar"), 1024, str(server_dir)),
        callbacks,
    )
    monkeypatch.setattr(core, "get_java_path", lambda: "java")
    monkeypatch.setattr(core.NetworkService, "is_port_available", lambda *_: False)

    instance.start()

    assert stopped == [-1]
    assert logs and logs[0][1] == "ERROR"
    assert instance.process is None


def test_shutdown_uses_forced_kill_after_timeout(tmp_path):
    callbacks = core.ServerCallbacks(lambda *_: None, lambda *_: None, lambda *_: None, lambda *_: None)
    instance = core.ServerInstance(
        core.ServerData("Test", "paper.jar", "paper.jar", 1024, str(tmp_path)),
        callbacks,
    )
    instance.process = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    instance.state = core.ServerState.ONLINE

    assert instance.shutdown(timeout=0.01) is False
    assert instance.process is None
