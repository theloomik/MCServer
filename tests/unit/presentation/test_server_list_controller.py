"""Tests for the server list controller, using in-memory backend pieces."""

import logging

import pytest
from fakes import InMemoryRepository, coordinator, management_for
from PySide6.QtWidgets import QApplication

from mcserver.domain.server_configuration import ServerConfiguration
from mcserver.presentation.controllers.server_list import (
    ServerListController,
    ServerListState,
    ServerRow,
    ServerStatus,
)
from mcserver.presentation.i18n import en

SURVIVAL = ServerConfiguration("survival", "survival", "paper.jar", 4096)
CREATIVE = ServerConfiguration("creative", "creative-files", "fabric.jar", 2048)


@pytest.fixture(autouse=True)
def _qt(qapp: QApplication) -> None:
    """Controllers are QObjects; keep a QApplication around."""


def controller_for(repository: InMemoryRepository, *, java: bool = True) -> tuple[ServerListController, list]:
    controller = ServerListController(management_for(repository), coordinator() if java else None)
    published: list[ServerListState] = []
    controller.state_changed.connect(published.append)
    return controller, published


def test_refresh_loads_servers_in_repository_order_with_stopped_status() -> None:
    controller, published = controller_for(InMemoryRepository(SURVIVAL, CREATIVE))

    controller.refresh()

    assert published[-1] == ServerListState(
        servers=(ServerRow(SURVIVAL, ServerStatus.STOPPED), ServerRow(CREATIVE, ServerStatus.STOPPED))
    )
    assert controller.state is published[-1]


def test_empty_collection_publishes_empty_state_without_error() -> None:
    controller, published = controller_for(InMemoryRepository())

    controller.refresh()

    assert published == [ServerListState()]


def test_select_loads_current_configuration_from_management() -> None:
    repository = InMemoryRepository(SURVIVAL, CREATIVE)
    controller, published = controller_for(repository)
    controller.refresh()
    edited = ServerConfiguration("creative", "creative-files", "purpur.jar", 6144)
    repository.items["creative"] = edited  # changed elsewhere after the list was loaded

    controller.select("creative")

    state = published[-1]
    assert state.selected == ServerRow(edited, ServerStatus.STOPPED)
    assert state.servers[1].configuration == edited
    assert state.details_error_key is None


def test_select_none_clears_selection_and_keeps_list() -> None:
    controller, published = controller_for(InMemoryRepository(SURVIVAL))
    controller.refresh()
    controller.select("survival")

    controller.select(None)

    assert published[-1].selected is None
    assert len(published[-1].servers) == 1


def test_refresh_preserves_selection_and_refreshes_its_details() -> None:
    repository = InMemoryRepository(SURVIVAL, CREATIVE)
    controller, published = controller_for(repository)
    controller.refresh()
    controller.select("survival")
    repository.items["survival"] = ServerConfiguration("survival", "survival", "paper.jar", 8192)

    controller.refresh()

    assert published[-1].selected is not None
    assert published[-1].selected.configuration.memory_mb == 8192


def test_refresh_clears_selection_when_server_disappeared() -> None:
    repository = InMemoryRepository(SURVIVAL, CREATIVE)
    controller, published = controller_for(repository)
    controller.refresh()
    controller.select("survival")
    del repository.items["survival"]

    controller.refresh()

    assert published[-1] == ServerListState(servers=(ServerRow(CREATIVE, ServerStatus.STOPPED),))


def test_selecting_a_server_deleted_elsewhere_reports_it_gone() -> None:
    repository = InMemoryRepository(SURVIVAL)
    controller, published = controller_for(repository)
    controller.refresh()
    del repository.items["survival"]

    controller.select("survival")

    assert published[-1].selected is None
    assert published[-1].details_error_key == "server_details.error.gone"


def test_storage_error_while_listing_is_reported_and_logged(caplog: pytest.LogCaptureFixture) -> None:
    repository = InMemoryRepository(SURVIVAL)
    repository.broken = True
    controller, published = controller_for(repository)

    with caplog.at_level(logging.ERROR):
        controller.refresh()

    assert published[-1] == ServerListState(list_error_key="server_list.error.load")
    assert "not valid JSON" in caplog.text


def test_storage_error_while_loading_details_keeps_the_list(caplog: pytest.LogCaptureFixture) -> None:
    repository = InMemoryRepository(SURVIVAL)
    controller, published = controller_for(repository)
    controller.refresh()
    repository.broken_get = True

    with caplog.at_level(logging.ERROR):
        controller.select("survival")

    assert published[-1].details_error_key == "server_details.error.load"
    assert len(published[-1].servers) == 1
    assert "not valid JSON" in caplog.text


def test_recovering_after_a_storage_error() -> None:
    repository = InMemoryRepository(SURVIVAL)
    repository.broken = True
    controller, published = controller_for(repository)
    controller.refresh()
    repository.broken = False

    controller.refresh()

    assert published[-1].list_error_key is None
    assert [row.server_id for row in published[-1].servers] == ["survival"]


def test_without_java_status_is_unknown_but_configurations_load() -> None:
    controller, published = controller_for(InMemoryRepository(SURVIVAL), java=False)

    controller.refresh()
    controller.select("survival")

    assert published[-1].selected == ServerRow(SURVIVAL, ServerStatus.UNKNOWN)


def test_active_server_shows_coordinator_state_and_others_stay_stopped() -> None:
    server_coordinator = coordinator()
    controller = ServerListController(management_for(InMemoryRepository(SURVIVAL, CREATIVE)), server_coordinator)
    server_coordinator.start_server("survival")

    controller.refresh()

    statuses = {row.server_id: row.status for row in controller.state.servers}
    assert statuses == {"survival": ServerStatus.RUNNING, "creative": ServerStatus.STOPPED}


def test_every_message_key_the_controller_can_publish_exists() -> None:
    keys = {"server_list.error.load", "server_details.error.gone", "server_details.error.load"}

    assert keys <= set(en.MESSAGES)
