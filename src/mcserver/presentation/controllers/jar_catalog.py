"""Pick and download an official server JAR in the background (M3-GUI-06)."""

from __future__ import annotations

from dataclasses import dataclass, replace
from threading import Event

from PySide6.QtCore import QObject, Qt, Signal

from mcserver.application.server_catalog import (
    CatalogVersion,
    DownloadCancelled,
    ServerDownload,
    ServerJarCatalog,
    ServerType,
)
from mcserver.presentation.errors import UserMessage, describe_error
from mcserver.presentation.workers import BackgroundRunner


@dataclass(frozen=True, slots=True)
class CatalogState:
    """What the download dialog shows."""

    server_type: ServerType = ServerType.PAPER
    include_unstable: bool = False
    versions: tuple[CatalogVersion, ...] = ()
    loading: bool = False
    selected: str | None = None
    download: ServerDownload | None = None
    """Details of the selected version, once resolved."""
    resolving: bool = False
    downloading: bool = False
    cancelling: bool = False
    path: str | None = None
    """The verified local file, after a successful download."""
    error: UserMessage | None = None

    @property
    def busy(self) -> bool:
        """Return whether a download is running (the dialog must stay open)."""
        return self.downloading

    @property
    def can_download(self) -> bool:
        """Return whether Download can start."""
        return self.download is not None and not self.downloading and not self.resolving


class JarCatalogController(QObject):
    """Load versions, resolve the selected one and download it; one request at a time per kind."""

    state_changed = Signal(object)  # CatalogState
    progress = Signal(int, int)
    downloaded = Signal(str)  # local path

    def __init__(self, catalog: ServerJarCatalog, background: BackgroundRunner, parent: QObject | None = None) -> None:
        """Use ``catalog`` through ``background``."""
        super().__init__(parent)
        self._catalog = catalog
        self._background = background
        self._state = CatalogState()
        self._generation = 0
        self._cancel = Event()
        self._relay = _ProgressRelay(self)
        self._relay.progress.connect(self.progress, Qt.ConnectionType.QueuedConnection)

    @property
    def state(self) -> CatalogState:
        """Return the current state."""
        return self._state

    def load(self, server_type: ServerType | None = None, include_unstable: bool | None = None) -> None:
        """Read the version list (again) for the chosen type."""
        if self._state.downloading:
            return
        state = replace(
            self._state,
            server_type=server_type or self._state.server_type,
            include_unstable=self._state.include_unstable if include_unstable is None else include_unstable,
            versions=(),
            loading=True,
            selected=None,
            download=None,
            error=None,
        )
        self._generation += 1
        generation = self._generation
        self._publish(state)
        catalog = self._catalog
        self._background.run(
            lambda: catalog.versions(state.server_type, state.include_unstable),
            lambda versions: self._loaded(generation, versions),
            lambda error: self._failed(generation, error),
        )

    def select(self, version: str | None) -> None:
        """Resolve the download details of ``version``."""
        if self._state.downloading or version == self._state.selected:
            return
        self._generation += 1
        generation = self._generation
        self._publish(replace(self._state, selected=version, download=None, resolving=version is not None, error=None))
        if version is None:
            return
        catalog, server_type = self._catalog, self._state.server_type
        self._background.run(
            lambda: catalog.resolve(server_type, version),
            lambda download: self._resolved(generation, download),
            lambda error: self._failed(generation, error),
        )

    def download(self) -> None:
        """Download and verify the selected JAR."""
        download = self._state.download
        if download is None or not self._state.can_download:
            return
        self._cancel.clear()
        self._publish(replace(self._state, downloading=True, error=None, path=None))
        catalog, relay, cancel = self._catalog, self._relay, self._cancel
        self._background.run(
            lambda: catalog.download(download, relay.report, cancel.is_set),
            self._downloaded,
            self._download_failed,
        )

    def cancel(self) -> None:
        """Ask the running download to stop; the partial file is removed."""
        if self._state.downloading:
            self._cancel.set()
            self._publish(replace(self._state, cancelling=True))

    def _loaded(self, generation: int, versions: tuple[CatalogVersion, ...]) -> None:
        if generation == self._generation:
            self._publish(replace(self._state, versions=versions, loading=False))

    def _resolved(self, generation: int, download: ServerDownload) -> None:
        if generation == self._generation:
            self._publish(replace(self._state, download=download, resolving=False))

    def _failed(self, generation: int, error: BaseException) -> None:
        if generation == self._generation:
            self._publish(replace(self._state, loading=False, resolving=False, error=describe_error(error)))

    def _downloaded(self, path: str) -> None:
        self._publish(replace(self._state, downloading=False, cancelling=False, path=path))
        self.downloaded.emit(path)

    def _download_failed(self, error: BaseException) -> None:
        message = None if isinstance(error, DownloadCancelled) else describe_error(error)
        self._publish(replace(self._state, downloading=False, cancelling=False, error=message))

    def _publish(self, state: CatalogState) -> None:
        self._state = state
        self.state_changed.emit(state)


class _ProgressRelay(QObject):
    progress = Signal(int, int)

    def report(self, done: int, total: int) -> None:
        self.progress.emit(done, total)


__all__ = ["CatalogState", "JarCatalogController"]
