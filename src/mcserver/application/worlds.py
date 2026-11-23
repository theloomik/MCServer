"""Worlds of a server: list, switch, create, import, export and delete (M3-BE-07)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from mcserver.application.errors import ServerIsRunning
from mcserver.application.ports import RemovedServerFiles, ServerConfigurationRepository
from mcserver.application.server_properties import ServerPropertiesService
from mcserver.domain.server_configuration import is_safe_name

DEFAULT_LEVEL_NAME = "world"
DIMENSION_SUFFIXES = ("_nether", "_the_end")
"""Paper and Spigot keep the Nether and the End in ``<level>_nether`` and ``<level>_the_end``."""
WorldProgress = Callable[[int, int], None]


class WorldError(RuntimeError):
    """Base class for world operations that cannot be done."""

    def __init__(self, server_id: str, name: str, message: str) -> None:
        """Remember which world of which server."""
        super().__init__(message)
        self.server_id = server_id
        self.name = name


class WorldNotFound(WorldError):
    """The world folder does not exist."""

    def __init__(self, server_id: str, name: str) -> None:
        """Name the missing world."""
        super().__init__(server_id, name, f"World {name!r} of {server_id!r} does not exist.")


class WorldAlreadyExists(WorldError):
    """A world or folder with that name exists already."""

    def __init__(self, server_id: str, name: str) -> None:
        """Name the world that exists."""
        super().__init__(server_id, name, f"{server_id!r} already has a folder named {name!r}.")


class WorldIsActive(WorldError):
    """The server's current world cannot be deleted (or exported while it runs)."""

    def __init__(self, server_id: str, name: str) -> None:
        """Name the active world."""
        super().__init__(server_id, name, f"{name!r} is the current world of {server_id!r}.")


class InvalidWorldName(WorldError):
    """The name cannot be used as a world folder."""

    def __init__(self, server_id: str, name: str) -> None:
        """Name the rejected name."""
        super().__init__(server_id, name, f"{name!r} is not a valid world name.")


class InvalidWorldSource(WorldError):
    """A folder or archive to import does not contain a Minecraft world."""

    def __init__(self, server_id: str, source: str, reason: str) -> None:
        """Explain why ``source`` cannot be imported."""
        super().__init__(server_id, source, f"{source} cannot be imported: {reason}")
        self.reason = reason


@dataclass(frozen=True, slots=True)
class WorldFolder:
    """One world as found on disk; ``folders`` are the main folder plus Paper's dimension folders."""

    name: str
    folders: tuple[str, ...]
    size_bytes: int
    modified_at: float
    """Newest modification time (POSIX seconds) of ``level.dat`` in any of the folders."""


@dataclass(frozen=True, slots=True)
class WorldInfo:
    """A world shown to the user."""

    name: str
    folders: tuple[str, ...]
    size_bytes: int
    modified_at: float
    active: bool


@dataclass(frozen=True, slots=True)
class WorldsOverview:
    """All worlds of a server and which one it uses."""

    server_id: str
    worlds: tuple[WorldInfo, ...]
    level_name: str
    level_exists: bool
    """``False`` when the server will generate ``level_name`` on its next start."""


class WorldStore(Protocol):
    """Read and change world folders inside a server folder; never deletes anything permanently."""

    def list_worlds(self, directory: str) -> tuple[WorldFolder, ...]:
        """Return the worlds in ``directory`` (folders with ``level.dat``), dimension folders grouped."""

    def folder_exists(self, directory: str, name: str) -> bool:
        """Return whether ``<directory>/<name>`` exists (as anything)."""

    def import_world(self, directory: str, source: str, name: str, progress: WorldProgress | None) -> None:
        """Copy the world in folder or ``.zip`` ``source`` to ``<directory>/<name>``; raise ``ValueError`` if it has none."""

    def export_world(
        self, directory: str, folders: tuple[str, ...], target: str, progress: WorldProgress | None
    ) -> None:
        """Write ``folders`` into the ZIP archive ``target``."""

    def remove_world(self, directory: str, folders: tuple[str, ...]) -> tuple[RemovedServerFiles, ...]:
        """Move ``folders`` to the Recycle Bin (or the trash folder)."""


class WorldService:
    """Manage the worlds of a server.

    The world a server uses is ``level-name`` in ``server.properties``. Switching
    to another world or creating a new one changes only that value, and only
    while the server is stopped; the server loads or generates it on the next
    start. The current world is never deleted, and it is not exported while the
    server runs (a backup is the consistent way to copy a running world).
    """

    def __init__(
        self,
        repository: ServerConfigurationRepository,
        store: WorldStore,
        properties: ServerPropertiesService,
        active_server: Callable[[], str | None],
    ) -> None:
        """Find server folders through ``repository``; ``active_server`` tells which server runs."""
        self._repository = repository
        self._store = store
        self._properties = properties
        self._active_server = active_server

    def overview(self, server_id: str) -> WorldsOverview:
        """Return the worlds of ``server_id`` and the one it uses."""
        directory = self._repository.get(server_id).directory
        level = self._level_name(server_id)
        found = self._store.list_worlds(directory)
        worlds = tuple(
            WorldInfo(world.name, world.folders, world.size_bytes, world.modified_at, world.name == level)
            for world in sorted(found, key=lambda world: (world.name != level, world.name.lower()))
        )
        return WorldsOverview(server_id, worlds, level, any(world.active for world in worlds))

    def use_world(self, server_id: str, name: str) -> None:
        """Make the existing world ``name`` the one ``server_id`` loads on its next start."""
        self._require_stopped(server_id)
        if name not in {world.name for world in self._worlds(server_id)}:
            raise WorldNotFound(server_id, name)
        self._properties.save(server_id, {"level-name": name})

    def create_world(self, server_id: str, name: str, seed: str = "") -> None:
        """Let ``server_id`` generate a new world ``name`` (with ``seed``) on its next start."""
        self._require_stopped(server_id)
        self._require_new_name(server_id, name)
        changes = {"level-name": name, "level-seed": seed.strip()}
        self._properties.save(server_id, changes)

    def import_world(self, server_id: str, source: str, name: str, progress: WorldProgress | None = None) -> None:
        """Copy a world from a folder or ``.zip`` file into ``server_id`` as ``name`` (not made current)."""
        self._require_new_name(server_id, name)
        directory = self._repository.get(server_id).directory
        try:
            self._store.import_world(directory, source, name, progress)
        except ValueError as error:
            raise InvalidWorldSource(server_id, source, str(error)) from error

    def export_world(self, server_id: str, name: str, target: str, progress: WorldProgress | None = None) -> None:
        """Write world ``name`` (with its dimension folders) into the ZIP file ``target``."""
        world = self._world(server_id, name)
        if world.name == self._level_name(server_id) and self._active_server() == server_id:
            raise WorldIsActive(server_id, name)
        self._store.export_world(self._repository.get(server_id).directory, world.folders, target, progress)

    def delete_world(self, server_id: str, name: str) -> tuple[RemovedServerFiles, ...]:
        """Move world ``name`` to the Recycle Bin; the current world is refused."""
        world = self._world(server_id, name)
        if world.name == self._level_name(server_id):
            raise WorldIsActive(server_id, name)
        return self._store.remove_world(self._repository.get(server_id).directory, world.folders)

    def suggest_name(self, server_id: str, base: str) -> str:
        """Return ``base`` (made safe) or ``base-2``, ``base-3``… so that no folder has that name yet."""
        cleaned = "".join(char if char.isalnum() or char in "-_" else "_" for char in base.strip())[:40]
        cleaned = cleaned.strip("._") or DEFAULT_LEVEL_NAME
        directory = self._repository.get(server_id).directory
        candidate, number = cleaned, 2
        while self._store.folder_exists(directory, candidate):
            candidate = f"{cleaned}-{number}"
            number += 1
        return candidate

    def _worlds(self, server_id: str) -> tuple[WorldFolder, ...]:
        return self._store.list_worlds(self._repository.get(server_id).directory)

    def _world(self, server_id: str, name: str) -> WorldFolder:
        for world in self._worlds(server_id):
            if world.name == name:
                return world
        raise WorldNotFound(server_id, name)

    def _level_name(self, server_id: str) -> str:
        value = self._properties.load(server_id).values.get("level-name", "").strip()
        return value or DEFAULT_LEVEL_NAME

    def _require_stopped(self, server_id: str) -> None:
        if self._active_server() == server_id:
            raise ServerIsRunning(server_id)

    def _require_new_name(self, server_id: str, name: str) -> None:
        if not is_safe_name(name) or name.endswith(DIMENSION_SUFFIXES) or name.startswith("."):
            raise InvalidWorldName(server_id, name)
        if self._store.folder_exists(self._repository.get(server_id).directory, name):
            raise WorldAlreadyExists(server_id, name)
