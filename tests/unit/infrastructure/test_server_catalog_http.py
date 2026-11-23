"""Mojang and PaperMC catalogs and the verified download cache, with a fake HTTP client (M3-BE-06)."""

from __future__ import annotations

import hashlib
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from mcserver.application.server_catalog import (
    CatalogUnavailable,
    DownloadCancelled,
    DownloadFailed,
    ServerDownload,
    ServerJarCatalog,
    ServerType,
)
from mcserver.infrastructure.server_catalog_http import (
    MOJANG_MANIFEST,
    PAPER_PROJECT,
    DownloadCache,
    MojangCatalog,
    PaperCatalog,
    _checked,
    _CheckedRedirects,
)

JAR = b"PK\x03\x04 a server jar" * 1000


class FakeClient:
    def __init__(self, documents: dict[str, Any] | None = None, body: bytes = JAR) -> None:
        self.documents = documents or {}
        self.body = body
        self.requested: list[str] = []
        self.streamed: list[str] = []

    def get_json(self, url: str) -> Any:
        self.requested.append(url)
        if url not in self.documents:
            raise CatalogUnavailable("the server answered 404 Not Found")
        return self.documents[url]

    def stream(self, url: str) -> Iterator[bytes]:
        _checked(url)
        self.streamed.append(url)
        for start in range(0, len(self.body), 4096):
            yield self.body[start : start + 4096]


MANIFEST = {
    "latest": {"release": "1.21.11"},
    "versions": [
        {"id": "26.1-snapshot-1", "type": "snapshot", "url": "https://piston-meta.mojang.com/v1/s.json"},
        {"id": "1.21.11", "type": "release", "url": "https://piston-meta.mojang.com/v1/r.json"},
        {"id": "b1.7.3", "type": "old_beta", "url": "https://piston-meta.mojang.com/v1/b.json"},
    ],
}
RELEASE = {
    "downloads": {
        "server": {
            "sha1": hashlib.sha1(JAR, usedforsecurity=False).hexdigest(),
            "size": len(JAR),
            "url": "https://piston-data.mojang.com/v1/objects/abc/server.jar",
        }
    },
    "javaVersion": {"majorVersion": 21},
}
PAPER = {"project": {"id": "paper"}, "versions": {"26.1": ["26.1-rc-2"], "1.21": ["1.21.11", "1.21.11-pre5"]}}
PAPER_BUILD = {
    "id": 132,
    "channel": "STABLE",
    "downloads": {
        "server:default": {
            "name": "paper-1.21.11-132.jar",
            "checksums": {"sha256": hashlib.sha256(JAR).hexdigest()},
            "size": len(JAR),
            "url": "https://fill-data.papermc.io/v1/objects/abc/paper-1.21.11-132.jar",
        }
    },
}
PAPER_VERSION = {"version": {"id": "1.21.11", "java": {"version": {"minimum": 21}}}}


def test_mojang_lists_releases_and_snapshots_and_resolves_the_server_jar() -> None:
    client = FakeClient({MOJANG_MANIFEST: MANIFEST, "https://piston-meta.mojang.com/v1/r.json": RELEASE})
    catalog = MojangCatalog(client)  # type: ignore[arg-type]
    versions = catalog.versions()
    assert [(version.version, version.stable) for version in versions] == [
        ("26.1-snapshot-1", False),
        ("1.21.11", True),
    ]
    download = catalog.resolve("1.21.11")
    assert download.file_name == "minecraft_server.1.21.11.jar" and download.java_major == 21
    assert download.checksum_algorithm == "sha1" and download.size_bytes == len(JAR)


def test_mojang_without_server_download_is_reported() -> None:
    client = FakeClient({MOJANG_MANIFEST: MANIFEST, "https://piston-meta.mojang.com/v1/s.json": {"downloads": {}}})
    with pytest.raises(CatalogUnavailable, match="no server download"):
        MojangCatalog(client).resolve("26.1-snapshot-1")  # type: ignore[arg-type]
    with pytest.raises(CatalogUnavailable, match="not in Mojang"):
        MojangCatalog(client).resolve("9.9")  # type: ignore[arg-type]


def test_paper_marks_test_versions_and_resolves_the_latest_build() -> None:
    base = f"{PAPER_PROJECT}/versions/1.21.11"
    client = FakeClient({PAPER_PROJECT: PAPER, f"{base}/builds/latest": PAPER_BUILD, base: PAPER_VERSION})
    catalog = PaperCatalog(client)  # type: ignore[arg-type]
    assert [(version.version, version.stable) for version in catalog.versions()] == [
        ("26.1-rc-2", False),
        ("1.21.11", True),
        ("1.21.11-pre5", False),
    ]
    download = catalog.resolve("1.21.11")
    assert download.file_name == "paper-1.21.11-132.jar" and download.checksum_algorithm == "sha256"
    assert download.java_major == 21 and download.stable
    with pytest.raises(CatalogUnavailable):
        catalog.resolve("../../x")


def test_unexpected_catalog_data_is_reported_not_crashed() -> None:
    with pytest.raises(CatalogUnavailable, match="unexpected format"):
        PaperCatalog(FakeClient({PAPER_PROJECT: {"oops": 1}})).versions()  # type: ignore[arg-type]
    with pytest.raises(CatalogUnavailable, match="404"):
        MojangCatalog(FakeClient()).versions()  # type: ignore[arg-type]


def test_catalog_hides_test_versions_unless_asked() -> None:
    client = FakeClient({MOJANG_MANIFEST: MANIFEST})
    catalog = ServerJarCatalog({ServerType.VANILLA: MojangCatalog(client)}, DownloadCache(Path("."), client))  # type: ignore[arg-type]
    assert [version.version for version in catalog.versions(ServerType.VANILLA)] == ["1.21.11"]
    assert len(catalog.versions(ServerType.VANILLA, include_unstable=True)) == 2
    with pytest.raises(CatalogUnavailable):
        catalog.versions(ServerType.PAPER)


@pytest.mark.parametrize(
    "url",
    [
        "http://piston-data.mojang.com/x.jar",
        "https://example.com/x.jar",
        "file:///C:/x.jar",
        "https://evil.papermc.io.example/x",
    ],
)
def test_only_https_to_official_hosts_is_allowed(url: str) -> None:
    with pytest.raises(CatalogUnavailable, match="refusing"):
        _checked(url)
    with pytest.raises(CatalogUnavailable):
        _CheckedRedirects().redirect_request(None, None, 302, "Found", {}, url)


# --- download cache ------------------------------------------------------------------------------


def paper_download(**changes: Any) -> ServerDownload:
    values: dict[str, Any] = {
        "server_type": ServerType.PAPER,
        "version": "1.21.11",
        "file_name": "paper-1.21.11-132.jar",
        "url": "https://fill-data.papermc.io/v1/objects/abc/paper.jar",
        "size_bytes": len(JAR),
        "checksum_algorithm": "sha256",
        "checksum": hashlib.sha256(JAR).hexdigest(),
        "java_major": 21,
    }
    values.update(changes)
    return ServerDownload(**values)


def test_verified_download_is_kept_and_reused(tmp_path: Path) -> None:
    client = FakeClient()
    cache = DownloadCache(tmp_path, client)  # type: ignore[arg-type]
    progress: list[tuple[int, int]] = []
    path = Path(cache.fetch(paper_download(), lambda done, total: progress.append((done, total)), None))
    assert path == (tmp_path / ".downloads" / "paper-1.21.11-132.jar").resolve() and path.read_bytes() == JAR
    assert progress[-1] == (len(JAR), len(JAR))
    assert cache.fetch(paper_download(), None, None) == str(path)
    assert len(client.streamed) == 1  # the cached copy matched its checksum


@pytest.mark.parametrize(
    ("changes", "reason"),
    [({"checksum": "0" * 64}, "checksum"), ({"size_bytes": len(JAR) + 1}, "expected")],
)
def test_bad_download_leaves_nothing(tmp_path: Path, changes: dict[str, Any], reason: str) -> None:
    cache = DownloadCache(tmp_path, FakeClient())  # type: ignore[arg-type]
    with pytest.raises(DownloadFailed, match=reason):
        cache.fetch(paper_download(**changes), None, None)
    assert list((tmp_path / ".downloads").iterdir()) == []


def test_corrupt_cached_file_is_downloaded_again(tmp_path: Path) -> None:
    client = FakeClient()
    (tmp_path / ".downloads").mkdir()
    (tmp_path / ".downloads" / "paper-1.21.11-132.jar").write_bytes(b"broken")
    cache = DownloadCache(tmp_path, client)  # type: ignore[arg-type]
    assert Path(cache.fetch(paper_download(), None, None)).read_bytes() == JAR
    assert len(client.streamed) == 1


def test_cancelled_download_leaves_nothing(tmp_path: Path) -> None:
    cache = DownloadCache(tmp_path, FakeClient())  # type: ignore[arg-type]
    with pytest.raises(DownloadCancelled):
        cache.fetch(paper_download(), None, lambda: True)
    assert list((tmp_path / ".downloads").iterdir()) == []


def test_unsafe_names_and_hosts_are_refused(tmp_path: Path) -> None:
    cache = DownloadCache(tmp_path, FakeClient())  # type: ignore[arg-type]
    with pytest.raises(DownloadFailed, match="not safe"):
        cache.fetch(paper_download(file_name="../evil.jar"), None, None)
    with pytest.raises(DownloadFailed, match="refusing"):
        cache.fetch(paper_download(url="https://example.com/paper.jar"), None, None)
