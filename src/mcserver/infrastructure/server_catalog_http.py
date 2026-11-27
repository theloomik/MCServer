"""HTTPS clients for the Mojang and PaperMC catalogs and a verified download cache (M3-BE-06).

Only HTTPS requests to the official hosts below are made. Requests carry a
generic User-Agent and no information about the user or their servers.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import urllib.error
import urllib.request
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from mcserver.application.server_catalog import (
    Cancelled,
    CatalogUnavailable,
    CatalogVersion,
    DownloadCancelled,
    DownloadFailed,
    DownloadProgress,
    ServerDownload,
    ServerType,
)
from mcserver.domain.server_configuration import is_safe_name

_logger = logging.getLogger(__name__)

USER_AGENT = "MCServer/2.0"
TIMEOUT_SECONDS = 20.0
_CHUNK = 256 * 1024
ALLOWED_HOSTS = frozenset(
    {
        "piston-meta.mojang.com",
        "piston-data.mojang.com",
        "launcher.mojang.com",
        "fill.papermc.io",
        "fill-data.papermc.io",
    }
)
MOJANG_MANIFEST = "https://piston-meta.mojang.com/mc/game/version_manifest_v2.json"
PAPER_PROJECT = "https://fill.papermc.io/v3/projects/paper"
DOWNLOADS_DIRECTORY = ".downloads"
_UNSTABLE = re.compile(r"-(rc|pre|snapshot)|^\d+w\d+[a-z]$", re.IGNORECASE)


def _checked(url: str) -> str:
    parts = urlsplit(url)
    if parts.scheme != "https" or parts.hostname not in ALLOWED_HOSTS:
        raise CatalogUnavailable(f"refusing to contact {parts.scheme}://{parts.hostname}")
    return url


class _CheckedRedirects(urllib.request.HTTPRedirectHandler):
    """Follow redirects only to the official hosts, over HTTPS."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]  # noqa: ANN001
        """Refuse a redirect that leaves ``ALLOWED_HOSTS``."""
        _checked(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class HttpClient:
    """Minimal HTTPS client restricted to ``ALLOWED_HOSTS`` (redirects included)."""

    def __init__(self, timeout: float = TIMEOUT_SECONDS) -> None:
        """Use ``timeout`` seconds for connecting and for each read."""
        self._timeout = timeout
        self._opener = urllib.request.build_opener(_CheckedRedirects())

    def _open(self, url: str):  # type: ignore[no-untyped-def]
        request = urllib.request.Request(_checked(url), headers={"User-Agent": USER_AGENT})
        # The scheme and host were checked above: only https to the official catalog hosts.
        return self._opener.open(request, timeout=self._timeout)  # nosec B310

    def get_json(self, url: str) -> Any:
        """Return the decoded JSON at ``url``; raise ``CatalogUnavailable``."""
        try:
            with self._open(url) as response:
                return json.loads(response.read().decode("utf-8"))
        except CatalogUnavailable:
            raise
        except (OSError, ValueError) as error:  # URLError and HTTPError are OSErrors
            raise CatalogUnavailable(_describe(error)) from error

    def stream(self, url: str) -> Iterator[bytes]:
        """Yield the body of ``url`` in chunks; raise ``CatalogUnavailable`` if it cannot be opened."""
        try:
            response = self._open(url)
        except CatalogUnavailable:
            raise
        except OSError as error:
            raise CatalogUnavailable(_describe(error)) from error
        with response:
            while chunk := response.read(_CHUNK):
                yield chunk


def _describe(error: BaseException) -> str:
    if isinstance(error, urllib.error.HTTPError):
        return f"the server answered {error.code} {error.reason}"
    if isinstance(error, urllib.error.URLError):
        return f"no connection ({error.reason})"
    return str(error) or type(error).__name__


def _field(data: Any, *path: str) -> Any:
    for key in path:
        if not isinstance(data, dict) or key not in data:
            raise CatalogUnavailable("the catalog returned data in an unexpected format")
        data = data[key]
    return data


class MojangCatalog:
    """Vanilla server JARs from Mojang's version manifest."""

    def __init__(self, client: HttpClient) -> None:
        """Read through ``client``."""
        self._client = client
        self._urls: dict[str, str] = {}

    def versions(self) -> tuple[CatalogVersion, ...]:
        """Return releases and snapshots, newest first."""
        entries = _field(self._client.get_json(MOJANG_MANIFEST), "versions")
        found: list[CatalogVersion] = []
        for entry in entries if isinstance(entries, list) else ():
            if not isinstance(entry, dict) or entry.get("type") not in ("release", "snapshot"):
                continue  # old_alpha / old_beta have no usable server
            version, url = entry.get("id"), entry.get("url")
            if isinstance(version, str) and isinstance(url, str):
                self._urls[version] = url
                found.append(CatalogVersion(ServerType.VANILLA, version, entry["type"] == "release"))
        return tuple(found)

    def resolve(self, version: str) -> ServerDownload:
        """Return the server JAR of ``version``."""
        if version not in self._urls:
            self.versions()
        url = self._urls.get(version)
        if url is None:
            raise CatalogUnavailable(f"Minecraft {version} is not in Mojang's version list")
        data = self._client.get_json(url)
        server = data.get("downloads", {}).get("server") if isinstance(data, dict) else None
        if not isinstance(server, dict):
            raise CatalogUnavailable(f"Mojang offers no server download for {version}")
        java = data.get("javaVersion", {}).get("majorVersion") if isinstance(data.get("javaVersion"), dict) else None
        return ServerDownload(
            ServerType.VANILLA,
            version,
            f"minecraft_server.{version}.jar",
            str(_field(server, "url")),
            int(server["size"]) if isinstance(server.get("size"), int) else None,
            "sha1",
            str(_field(server, "sha1")).lower(),
            java if isinstance(java, int) else None,
        )


class PaperCatalog:
    """Paper server JARs from PaperMC's Fill API (v3)."""

    def __init__(self, client: HttpClient) -> None:
        """Read through ``client``."""
        self._client = client

    def versions(self) -> tuple[CatalogVersion, ...]:
        """Return Paper versions, newest first."""
        groups = _field(self._client.get_json(PAPER_PROJECT), "versions")
        if not isinstance(groups, dict):
            raise CatalogUnavailable("the catalog returned data in an unexpected format")
        return tuple(
            CatalogVersion(ServerType.PAPER, version, not _UNSTABLE.search(version))
            for group in groups.values()
            if isinstance(group, list)
            for version in group
            if isinstance(version, str)
        )

    def resolve(self, version: str) -> ServerDownload:
        """Return the latest build of ``version``."""
        if not re.fullmatch(r"[0-9A-Za-z.\-]+", version):
            raise CatalogUnavailable(f"{version!r} is not a Paper version")
        base = f"{PAPER_PROJECT}/versions/{version}"
        build = self._client.get_json(f"{base}/builds/latest")
        download = _field(build, "downloads", "server:default")
        java: int | None = None
        try:
            minimum = _field(self._client.get_json(base), "version", "java", "version", "minimum")
            java = minimum if isinstance(minimum, int) else None
        except CatalogUnavailable:
            _logger.info("Paper did not say which Java %s needs.", version)
        size = download.get("size") if isinstance(download, dict) else None
        return ServerDownload(
            ServerType.PAPER,
            version,
            str(_field(download, "name")),
            str(_field(download, "url")),
            size if isinstance(size, int) else None,
            "sha256",
            str(_field(download, "checksums", "sha256")).lower(),
            java,
            stable=_field(build, "channel") == "STABLE",
        )


class DownloadCache:
    """Keep verified JARs in ``<servers root>/.downloads``; a file is only kept when its checksum matches."""

    def __init__(self, servers_directory: Path, client: HttpClient) -> None:
        """Store files below ``servers_directory`` and download through ``client``."""
        self._folder = servers_directory.resolve() / DOWNLOADS_DIRECTORY
        self._client = client

    def fetch(self, download: ServerDownload, progress: DownloadProgress | None, cancelled: Cancelled | None) -> str:
        """Return a verified local copy of ``download``."""
        name = download.file_name
        if not is_safe_name(name) or not name.lower().endswith(".jar"):
            raise DownloadFailed(name, "the file name is not safe")
        target = self._folder / name
        if target.is_file() and _digest(target, download.checksum_algorithm) == download.checksum:
            return str(target)
        self._folder.mkdir(parents=True, exist_ok=True)
        partial = target.with_name(name + ".partial")
        hasher = _hasher(download.checksum_algorithm)
        done = 0
        total = download.size_bytes or 0
        try:
            with partial.open("wb") as writer:
                for chunk in self._client.stream(download.url):
                    if cancelled is not None and cancelled():
                        raise DownloadCancelled(name)
                    writer.write(chunk)
                    hasher.update(chunk)
                    done += len(chunk)
                    if progress is not None:
                        progress(done, total or done)
            if download.size_bytes is not None and done != download.size_bytes:
                raise DownloadFailed(name, f"expected {download.size_bytes} bytes but received {done}")
            if str(hasher.hexdigest()) != download.checksum:
                raise DownloadFailed(name, "the file does not match its official checksum")
            os.replace(partial, target)
        except CatalogUnavailable as error:
            raise DownloadFailed(name, error.reason) from error
        except OSError as error:
            raise DownloadFailed(name, f"the file could not be saved: {error}") from error
        finally:
            # Only the unfinished download MCServer itself was writing; a verified file was renamed already.
            partial.unlink(missing_ok=True)
        return str(target)


def _digest(path: Path, algorithm: str) -> str:
    hasher = _hasher(algorithm)
    with path.open("rb") as reader:
        while chunk := reader.read(_CHUNK):
            hasher.update(chunk)
    return str(hasher.hexdigest())


def _hasher(algorithm: str):  # type: ignore[no-untyped-def]
    """Return a hash object for checking a download against the publisher's checksum (not for security)."""
    if algorithm not in ("sha1", "sha256"):
        raise DownloadFailed("?", f"unsupported checksum {algorithm}")
    return hashlib.new(algorithm, usedforsecurity=False)
