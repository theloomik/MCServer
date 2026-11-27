"""Choose and download official server JARs: Vanilla from Mojang, Paper from PaperMC (M3-BE-06)."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Protocol

from mcserver.application.progress import CancelToken, OperationCancelled, ProgressReporter, Stage, stage_callback

DownloadProgress = Callable[[int, int], None]
"""Called with (bytes downloaded, total bytes)."""
Cancelled = Callable[[], bool]


class ServerType(str, Enum):
    """Server software MCServer can download."""

    PAPER = "paper"
    VANILLA = "vanilla"


@dataclass(frozen=True, slots=True)
class CatalogVersion:
    """One Minecraft version offered for a server type, newest first in lists."""

    server_type: ServerType
    version: str
    stable: bool
    """``False`` for snapshots, pre-releases and release candidates."""


@dataclass(frozen=True, slots=True)
class ServerDownload:
    """Everything needed to download and verify one server JAR."""

    server_type: ServerType
    version: str
    file_name: str
    url: str
    size_bytes: int | None
    checksum_algorithm: str
    """``sha1`` (Mojang) or ``sha256`` (PaperMC)."""
    checksum: str
    java_major: int | None
    """The Java version the server needs, when the source says so."""
    stable: bool = True
    """``False`` for an experimental Paper build."""


class CatalogError(RuntimeError):
    """Base class for catalog and download problems."""


class CatalogUnavailable(CatalogError):
    """The version list or download details could not be read (offline, service down, unexpected data)."""

    def __init__(self, reason: str) -> None:
        """Explain what failed."""
        super().__init__(reason)
        self.reason = reason


class DownloadFailed(CatalogError):
    """The download did not complete, or the file did not match its checksum; nothing was kept."""

    def __init__(self, file_name: str, reason: str) -> None:
        """Name the file and the reason."""
        super().__init__(f"{file_name}: {reason}")
        self.file_name = file_name
        self.reason = reason


class DownloadCancelled(CatalogError, OperationCancelled):
    """The user cancelled the download; nothing was kept."""


class CatalogSource(Protocol):
    """Versions and download details of one server type."""

    def versions(self) -> tuple[CatalogVersion, ...]:
        """Return all versions, newest first; raise ``CatalogUnavailable``."""

    def resolve(self, version: str) -> ServerDownload:
        """Return the download of ``version`` (latest build for Paper); raise ``CatalogUnavailable``."""


class DownloadStore(Protocol):
    """Download a verified JAR into a local cache."""

    def fetch(self, download: ServerDownload, progress: DownloadProgress | None, cancelled: Cancelled | None) -> str:
        """Return the path of the verified file, reusing a cached copy whose checksum matches."""


class ServerJarCatalog:
    """List versions, resolve downloads and download verified server JARs."""

    def __init__(self, sources: Mapping[ServerType, CatalogSource], store: DownloadStore) -> None:
        """Use one ``CatalogSource`` per server type and ``store`` for the files."""
        self._sources = dict(sources)
        self._store = store

    @property
    def server_types(self) -> tuple[ServerType, ...]:
        """Return the server types that can be downloaded."""
        return tuple(self._sources)

    def versions(self, server_type: ServerType, include_unstable: bool = False) -> tuple[CatalogVersion, ...]:
        """Return the versions of ``server_type``, newest first (stable ones unless asked)."""
        found = self._source(server_type).versions()
        return found if include_unstable else tuple(version for version in found if version.stable)

    def resolve(self, server_type: ServerType, version: str) -> ServerDownload:
        """Return what downloading ``version`` involves (file, size, checksum, Java)."""
        return self._source(server_type).resolve(version)

    def download(
        self, download: ServerDownload, progress: ProgressReporter | None = None, cancel: CancelToken | None = None
    ) -> str:
        """Download and verify ``download``; return the local file to create a server from."""
        cancelled = (lambda: cancel.cancelled) if cancel is not None else None
        return self._store.fetch(download, stage_callback(Stage.DOWNLOADING, progress, None), cancelled)

    def _source(self, server_type: ServerType) -> CatalogSource:
        try:
            return self._sources[server_type]
        except KeyError:
            raise CatalogUnavailable(f"{server_type.value} servers cannot be downloaded") from None
