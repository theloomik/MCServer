import json
import socket

import pytest

from services import AtomicJsonStore, NetworkService, ServerPathPolicy


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
