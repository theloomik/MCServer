import json
import socket

import pytest

from services import AtomicJsonStore, NetworkService, PlayitDownloader, PlayitInstance, ServerPathPolicy


def test_path_policy_rejects_paths_outside_root(tmp_path):
    policy = ServerPathPolicy(tmp_path / "servers")

    assert policy.directory_for_name("Survival").parent == policy.servers_dir
    for invalid_name in ("../outside", r"..\outside", "/absolute", "bad/name", "bad:name"):
        with pytest.raises(ValueError):
            policy.directory_for_name(invalid_name)


def test_atomic_json_write_preserves_previous_file_on_error(tmp_path):
    path = tmp_path / "settings.json"
    AtomicJsonStore.write(path, {"state": "valid"})

    with pytest.raises(TypeError):
        AtomicJsonStore.write(path, {"invalid": object()})

    assert json.loads(path.read_text(encoding="utf-8")) == {"state": "valid"}


def test_network_service_detects_busy_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]

        assert not NetworkService.is_port_available("127.0.0.1", port)

    assert NetworkService.is_port_available("127.0.0.1", port)


def test_playit_pe_validation(tmp_path):
    fake = tmp_path / "playit.exe"
    fake.write_bytes(b"MZ" + b"\0" * 62)
    assert not PlayitDownloader._is_valid_pe(fake)

    valid = tmp_path / "valid.exe"
    header = bytearray(128)
    header[0:2] = b"MZ"
    header[60:64] = (80).to_bytes(4, "little")
    header[80:84] = b"PE\0\0"
    valid.write_bytes(header)
    assert PlayitDownloader._is_valid_pe(valid)


def test_playit_download_rejects_untrusted_url(monkeypatch):
    def _fake():
        return "http://evil.com/playit.exe", "v0.0.0", None

    monkeypatch.setattr(PlayitDownloader, "fetch_latest_windows_asset", staticmethod(_fake))
    with pytest.raises(ValueError, match="untrusted"):
        PlayitDownloader.download()


def test_playit_addr_regex():
    pattern = PlayitInstance._ADDR_RE
    assert pattern.search("tcp tunnel: try.joinmc.link:25565")
    assert pattern.search("address: abc123.joinmc.link:12345")
    assert pattern.search("tunnel at xyz.playit.gg:25565")
    assert not pattern.search("localhost:25565")
    assert not pattern.search("192.168.1.1:25565")


def test_playit_field_addr_regex():
    pattern = PlayitInstance._FIELD_ADDR_RE
    assert pattern.search("addr=try.joinmc.link:25565")
    assert pattern.search("tunnel_addr=abc.ply.gg:12345")
    assert pattern.search("public=my-server.joinmc.link:25565")
    assert not pattern.search("addr=127.0.0.1:25565")  # loopback filtered at instance level
