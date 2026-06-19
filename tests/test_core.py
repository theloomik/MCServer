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


def test_server_start_rejects_missing_jar(tmp_path, monkeypatch):
    server_dir = tmp_path / "server"
    server_dir.mkdir()
    logs = []
    stopped = []
    callbacks = core.ServerCallbacks(lambda text, level: logs.append((text, level)), lambda *_: None, lambda *_: None, stopped.append)
    instance = core.ServerInstance(
        core.ServerData("Test", "missing.jar", str(server_dir / "missing.jar"), 1024, str(server_dir)),
        callbacks,
    )
    monkeypatch.setattr(core, "get_java_path", lambda: "java")

    instance.start()

    assert stopped == [-1]
    assert instance.process is None
    assert any("missing" in text.lower() for text, _level in logs)


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


def test_corrupt_config_is_backed_up_and_not_silent(tmp_path):
    servers_dir = tmp_path / "servers"
    servers_dir.mkdir()
    config = servers_dir / "servers_config.json"
    config.write_text("{broken", encoding="utf-8")

    manager = core.ServerManager(str(servers_dir))

    assert manager.servers == {}
    assert manager.last_config_error
    assert not config.exists()
    assert list(servers_dir.glob("servers_config.json.corrupt-*.bak"))
    manager.cleanup()


def test_invalid_ram_in_config_falls_back_to_safe_default(tmp_path):
    servers_dir = tmp_path / "servers"
    servers_dir.mkdir()
    (servers_dir / "servers_config.json").write_text(
        json.dumps({
            "Survival": {
                "name": "Survival",
                "core_name": "paper.jar",
                "jar_path": "paper.jar",
                "ram": "nope",
                "directory": str(servers_dir / "Survival"),
            }
        }),
        encoding="utf-8",
    )

    manager = core.ServerManager(str(servers_dir))

    assert manager.servers["Survival"].ram == 1024
    manager.cleanup()


def test_properties_reader_falls_back_to_latin1(tmp_path):
    # \xff is invalid UTF-8 but valid latin-1 (ÿ) — file should still be readable
    props = tmp_path / "server.properties"
    props.write_bytes(b"server-port=25565\n\xff")

    result = core.read_properties_file(props)
    assert result.get("server-port") == "25565"


def test_save_server_properties_preserves_comments_and_updates_atomically(tmp_path):
    manager = make_manager(tmp_path)
    server_dir = manager.servers_dir / "Survival"
    server_dir.mkdir()
    props = server_dir / "server.properties"
    props.write_text("# hello\nmax-players=20\nmotd=old\n", encoding="utf-8")
    manager.servers["Survival"] = core.ServerData("Survival", "paper.jar", "paper.jar", 1024, str(server_dir))

    manager.save_server_properties("Survival", {"max-players": "10"})

    assert props.read_text(encoding="utf-8") == "# hello\nmax-players=10\nmotd=old\n"
    manager.cleanup()
