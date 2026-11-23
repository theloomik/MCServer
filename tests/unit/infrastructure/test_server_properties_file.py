"""server.properties round trip and validation (M3-QA-02, M3-BE-01)."""

from __future__ import annotations

import socket
from pathlib import Path

import pytest

from mcserver.application.server_properties import ServerPropertiesService
from mcserver.domain.server_properties import InvalidServerProperties, normalize_property, validate_properties
from mcserver.infrastructure.server_configuration import server_address
from mcserver.infrastructure.server_properties_file import port_in_use, read_properties, write_properties

VANILLA = (
    "#Minecraft server properties\r\n"
    "#Mon Nov 23 18:30:00 EET 2026\r\n"
    "enable-command-block=false\r\n"
    "gamemode=survival\r\n"
    "level-name=world\r\n"
    "motd=A Minecraft Server\r\n"
    "max-players=20\r\n"
    "server-port=25565\r\n"
)


def test_reading_decodes_java_properties_escapes(tmp_path: Path) -> None:
    path = tmp_path / "server.properties"
    path.write_text(
        "motd=\\u00A7aHello \\u0421\\u0435\\u0440\\u0432\\u0435\\u0440\nlevel-seed=a\\:b\nkey : value\n",
        encoding="latin-1",
    )

    values = read_properties(path).values

    assert values["motd"] == "§aHello Сервер"
    assert values["level-seed"] == "a:b"
    assert values["key"] == "value"


def test_untouched_lines_stay_byte_for_byte_and_crlf_is_kept(tmp_path: Path) -> None:
    path = tmp_path / "server.properties"
    path.write_bytes(VANILLA.encode("utf-8"))

    write_properties(path, {"max-players": "50", "difficulty": "hard"})

    data = path.read_bytes().decode("utf-8")
    expected = VANILLA.replace("max-players=20\r\n", "max-players=50\r\n") + "difficulty=hard\r\n"
    assert data == expected


def test_non_ascii_values_are_written_as_unicode_escapes_and_read_back(tmp_path: Path) -> None:
    path = tmp_path / "server.properties"
    path.write_text("motd=old\n", encoding="utf-8")

    write_properties(path, {"motd": "Сервер: тест = 1"})

    assert (
        path.read_text(encoding="ascii")
        == "motd=\\u0421\\u0435\\u0440\\u0432\\u0435\\u0440\\: \\u0442\\u0435\\u0441\\u0442 \\= 1\n"
    )
    assert read_properties(path).values["motd"] == "Сервер: тест = 1"


def test_latin1_files_are_kept_in_latin1(tmp_path: Path) -> None:
    path = tmp_path / "server.properties"
    path.write_bytes("motd=Caf\xe9\nmax-players=20\n".encode("latin-1"))

    write_properties(path, {"max-players": "30"})

    assert path.read_bytes() == "motd=Caf\xe9\nmax-players=30\n".encode("latin-1")


def test_missing_file_is_created_with_a_header(tmp_path: Path) -> None:
    path = tmp_path / "server.properties"
    assert not read_properties(path).exists

    write_properties(path, {"server-port": "25570"})

    assert read_properties(path).values == {"server-port": "25570"}
    assert path.read_text(encoding="utf-8").startswith("#")


@pytest.mark.parametrize(
    ("key", "value", "normalized"),
    [
        ("gamemode", " Creative ", "creative"),
        ("online-mode", "TRUE", "true"),
        ("max-players", " 50", "50"),
        ("motd", " keep spaces ", " keep spaces "),
    ],
)
def test_known_values_are_normalized(key: str, value: str, normalized: str) -> None:
    assert normalize_property(key, value) == normalized


def test_every_invalid_value_is_reported_at_once() -> None:
    with pytest.raises(InvalidServerProperties) as error:
        validate_properties(
            {
                "server-port": "70000",
                "gamemode": "god",
                "pvp": "maybe",
                "motd": "line\nbreak",
                "level-name": "../x",
                "view-distance": "abc",
            }
        )

    assert set(error.value.problems) == {"server-port", "gamemode", "pvp", "motd", "level-name", "view-distance"}


class Store:
    def __init__(self) -> None:
        self.written: list[dict[str, str]] = []

    def read(self, server_id: str):  # type: ignore[no-untyped-def]
        from mcserver.application.server_properties import ServerPropertiesDocument

        return ServerPropertiesDocument({"pvp": "true"}, True)

    def write(self, server_id: str, changes):  # type: ignore[no-untyped-def]
        self.written.append(dict(changes))


def test_service_validates_before_writing_and_reports_restart_needed() -> None:
    store = Store()
    service = ServerPropertiesService(store, lambda: "survival")

    assert service.load("survival").running
    assert service.save("survival", {"pvp": "FALSE"}) is True
    assert store.written == [{"pvp": "false"}]
    with pytest.raises(InvalidServerProperties):
        service.save("survival", {"pvp": "nope"})
    assert store.written == [{"pvp": "false"}]


def test_server_address_reads_ip_and_port_with_defaults(tmp_path: Path) -> None:
    assert server_address(tmp_path) == ("", 25565)
    (tmp_path / "server.properties").write_text("server-ip=127.0.0.1\nserver-port=25600\n", encoding="utf-8")
    assert server_address(tmp_path) == ("127.0.0.1", 25600)
    (tmp_path / "server.properties").write_text("server-port=nonsense\n", encoding="utf-8")
    assert server_address(tmp_path) == ("", 25565)


def test_port_in_use_detects_a_listener() -> None:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        port = listener.getsockname()[1]
        assert port_in_use("127.0.0.1", port)
    assert not port_in_use("127.0.0.1", port)
