"""Unit tests must not depend on which ports are free on the machine running them."""

import pytest


@pytest.fixture(autouse=True)
def free_ports(monkeypatch: pytest.MonkeyPatch) -> None:
    """Treat every server port as free."""
    monkeypatch.setattr("mcserver.infrastructure.server_configuration.port_in_use", lambda _host, _port: False)
