"""Worlds of the selected server (M3-GUI-07)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace

from PySide6.QtCore import QObject, Signal

from mcserver.application.ports import RemovedServerFiles
from mcserver.application.progress import CancelToken
from mcserver.application.worlds import WorldInfo, WorldService, WorldsOverview
from mcserver.presentation.errors import UserMessage, describe_error, error_tone
from mcserver.presentation.workers import BackgroundRunner, ProgressRelay


@dataclass(frozen=True, slots=True)
class WorldsState:
    """What the worlds view shows."""

    server_id: str | None = None
    worlds: tuple[WorldInfo, ...] = ()
    level_name: str = ""
    level_exists: bool = True
    server_active: bool = False
    loading: bool = False
    busy: bool = False
    cancellable: bool = False
    """The running import or export can be cancelled."""
    cancelling: bool = False
    message: UserMessage | None = None
    tone: str = "notice"

    @property
    def can_switch(self) -> bool:
        """Return whether the current world can be changed (only while the server is stopped)."""
        return self.server_id is not None and not self.busy and not self.server_active

    @property
    def can_change_files(self) -> bool:
        """Return whether imports, exports and deletes can start."""
        return self.server_id is not None and not self.busy


class WorldsController(QObject):
    """Run world operations in the background, one at a time, and keep the list current."""

    state_changed = Signal(object)  # WorldsState
    progress = Signal(object)  # Progress
    level_changed = Signal()
    """The current world (``level-name``) was changed."""

    def __init__(
        self, service: WorldService | None, background: BackgroundRunner, parent: QObject | None = None
    ) -> None:
        """Use ``service`` (``None`` disables the worlds tab)."""
        super().__init__(parent)
        self._service = service
        self._background = background
        self._state = WorldsState()
        self._load_generation = 0
        self._relay = ProgressRelay(self)
        self._relay.connect_to(self.progress)
        self._cancel: CancelToken | None = None

    @property
    def available(self) -> bool:
        """Return whether worlds can be managed at all."""
        return self._service is not None

    @property
    def state(self) -> WorldsState:
        """Return the current state."""
        return self._state

    @property
    def busy(self) -> bool:
        """Return whether a world operation is running."""
        return self._state.busy

    @property
    def service(self) -> WorldService | None:
        """Return the world use cases (for name suggestions in dialogs)."""
        return self._service

    def show_server(self, server_id: str | None) -> None:
        """Show the worlds of ``server_id``."""
        if server_id == self._state.server_id:
            return
        self._publish(WorldsState(server_id=server_id, server_active=False, busy=self._state.busy))
        self.refresh()

    def set_active_server(self, active_server_id: str | None) -> None:
        """Track whether the selected server is active."""
        active = active_server_id is not None and active_server_id == self._state.server_id
        if active != self._state.server_active:
            self._publish(replace(self._state, server_active=active))

    def refresh(self) -> None:
        """Read the worlds again in the background (sizes take a moment for large worlds)."""
        service, server_id = self._service, self._state.server_id
        if service is None or server_id is None:
            return
        self._load_generation += 1
        generation = self._load_generation
        self._publish(replace(self._state, loading=True))
        self._background.run(
            lambda: service.overview(server_id),
            lambda overview: self._loaded(generation, overview),
            lambda error: self._load_failed(generation, server_id, error),
        )

    def use_world(self, name: str) -> None:
        """Make ``name`` the current world (from the next start)."""
        self._run(
            lambda service, server_id, _cancel: service.use_world(server_id, name),
            lambda _result: UserMessage("worlds.used", {"name": name}),
            switch=True,
        )

    def create_world(self, name: str, seed: str) -> None:
        """Let the server generate a new world ``name`` on its next start."""
        self._run(
            lambda service, server_id, _cancel: service.create_world(server_id, name, seed),
            lambda _result: UserMessage("worlds.created", {"name": name}),
            switch=True,
        )

    def import_world(self, source: str, name: str) -> None:
        """Copy a world from a folder or ZIP file."""
        relay = self._relay
        self._run(
            lambda service, server_id, cancel: service.import_world(server_id, source, name, relay.report, cancel),
            lambda _result: UserMessage("worlds.imported", {"name": name}),
            cancellable=True,
        )

    def export_world(self, name: str, target: str) -> None:
        """Write world ``name`` into the ZIP file ``target``."""
        relay = self._relay
        self._run(
            lambda service, server_id, cancel: service.export_world(server_id, name, target, relay.report, cancel),
            lambda _result: UserMessage("worlds.exported", {"name": name, "path": target}),
            cancellable=True,
        )

    def delete_world(self, name: str) -> None:
        """Move world ``name`` to the Recycle Bin."""

        def message(result: object) -> UserMessage:
            removed: tuple[RemovedServerFiles, ...] = result if isinstance(result, tuple) else ()
            trash = [item.location for item in removed if item.kind == "trash"]
            if trash:
                return UserMessage("worlds.deleted_trash", {"name": name, "location": trash[0]})
            return UserMessage("worlds.deleted", {"name": name})

        self._run(lambda service, server_id, _cancel: service.delete_world(server_id, name), message)

    def cancel(self) -> None:
        """Ask the running import or export to stop; its partial copy or archive is removed."""
        if self._cancel is None or not self._state.busy or not self._state.cancellable:
            return
        self._cancel.cancel()
        self._publish(replace(self._state, cancelling=True))

    def _run(
        self,
        action: Callable[[WorldService, str, CancelToken], object],
        success: Callable[[object], UserMessage],
        *,
        switch: bool = False,
        cancellable: bool = False,
    ) -> None:
        service, server_id = self._service, self._state.server_id
        allowed = self._state.can_switch if switch else self._state.can_change_files
        if service is None or server_id is None or not allowed:
            return
        cancel = self._cancel = CancelToken()
        self._publish(
            replace(
                self._state,
                busy=True,
                cancellable=cancellable,
                cancelling=False,
                message=UserMessage("worlds.working"),
                tone="notice",
            )
        )

        def done(result: object) -> None:
            self._finish(success(result), "success")
            if switch:
                self.level_changed.emit()

        self._background.run(lambda: action(service, server_id, cancel), done, self._fail)

    def _finish(self, message: UserMessage, tone: str) -> None:
        self._cancel = None
        self._publish(replace(self._state, busy=False, cancellable=False, cancelling=False, message=message, tone=tone))
        self.refresh()

    def _fail(self, error: BaseException) -> None:
        self._finish(describe_error(error), error_tone(error))

    def _loaded(self, generation: int, overview: WorldsOverview) -> None:
        if generation != self._load_generation or overview.server_id != self._state.server_id:
            return
        self._publish(
            replace(
                self._state,
                worlds=overview.worlds,
                level_name=overview.level_name,
                level_exists=overview.level_exists,
                loading=False,
            )
        )

    def _load_failed(self, generation: int, server_id: str, error: BaseException) -> None:
        if generation != self._load_generation or server_id != self._state.server_id:
            return
        self._publish(replace(self._state, loading=False, message=describe_error(error), tone="error"))

    def _publish(self, state: WorldsState) -> None:
        self._state = state
        self.state_changed.emit(state)


__all__ = ["WorldsController", "WorldsState"]
