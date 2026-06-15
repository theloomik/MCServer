import hashlib
import json
import os
import socket
import tempfile
import urllib.request
from pathlib import Path
from typing import Any


class AtomicJsonStore:
    @staticmethod
    def write(path: Path, data: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = None
        try:
            with tempfile.NamedTemporaryFile(
                "w", encoding="utf-8", dir=path.parent, delete=False, suffix=".tmp"
            ) as temp_file:
                temp_path = Path(temp_file.name)
                json.dump(data, temp_file, indent=2, ensure_ascii=False)
                temp_file.flush()
                os.fsync(temp_file.fileno())
            os.replace(temp_path, path)
        finally:
            if temp_path and temp_path.exists():
                try:
                    temp_path.unlink()
                except OSError:
                    pass


class ServerPathPolicy:
    def __init__(self, servers_dir: Path):
        self.servers_dir = servers_dir.resolve()

    @staticmethod
    def is_valid_name(name: str) -> bool:
        if not isinstance(name, str) or not name or name in {".", ".."}:
            return False
        if name != name.strip() or name.endswith((".", " ")):
            return False
        return not any(ord(char) < 32 or char in '<>:"/\\|?*' for char in name)

    def directory_for_name(self, name: str) -> Path:
        if not self.is_valid_name(name):
            raise ValueError("Invalid server name")
        path = (self.servers_dir / name).resolve()
        if path.parent != self.servers_dir:
            raise ValueError("Server path escapes the managed directory")
        return path

    def require_managed_directory(self, directory: str) -> Path:
        path = Path(directory).resolve()
        if path.parent != self.servers_dir:
            raise ValueError("Server directory is outside the managed directory")
        return path


class NetworkService:
    @staticmethod
    def is_port_available(host: str, port: int) -> bool:
        # Minecraft binds all interfaces when server-ip is blank; the preflight must match it.
        bind_host = host.strip() or "0.0.0.0"  # nosec B104
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.bind((bind_host, port))
            return True
        except OSError:
            return False


class PlayitDownloader:
    """Downloads the latest playit.gg Windows executable from GitHub releases."""

    _GITHUB_API = "https://api.github.com/repos/playit-cloud/playit-agent/releases/latest"

    @staticmethod
    def fetch_latest_windows_asset() -> tuple[str, str]:
        """Returns (download_url, tag_name) for the latest Windows .exe asset."""
        req = urllib.request.Request(
            PlayitDownloader._GITHUB_API,
            headers={"User-Agent": "MCServer-App/1.0"},
        )
        with urllib.request.urlopen(req, timeout=15) as resp:  # nosec B310
            import json as _json
            data = _json.load(resp)
        tag: str = data.get("tag_name", "unknown")
        for asset in data.get("assets", []):
            name: str = asset.get("name", "").lower()
            if name.endswith(".exe") and ("windows" in name or name == "playit.exe"):
                return asset["browser_download_url"], tag
        raise ValueError(f"No Windows .exe asset found in release {tag}")

    @staticmethod
    def download_to(url: str, dest: Path) -> str:
        """Downloads *url* to *dest* and returns its SHA-256 hex digest.

        Raises ValueError if the downloaded file is not a valid Windows PE executable.
        """
        digest = hashlib.sha256()
        with urllib.request.urlopen(url, timeout=120) as resp:  # nosec B310
            with open(dest, "wb") as out:
                while True:
                    chunk = resp.read(65536)
                    if not chunk:
                        break
                    out.write(chunk)
                    digest.update(chunk)
        if not PlayitDownloader._is_valid_pe(dest):
            try:
                dest.unlink()
            except OSError:
                pass
            raise ValueError("Downloaded file is not a valid Windows executable (missing MZ header)")
        return digest.hexdigest()

    @staticmethod
    def _is_valid_pe(path: Path) -> bool:
        try:
            with open(path, "rb") as f:
                return f.read(2) == b"MZ"
        except OSError:
            return False
