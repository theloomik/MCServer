import hashlib
import json
import os
import re
import socket
import subprocess  # nosec B404
import sys
import tempfile
import threading
import urllib.request
from pathlib import Path
from typing import Any, Callable, Optional
from urllib.parse import urlparse


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
        bind_host = host.strip() or "0.0.0.0"  # nosec B104
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.bind((bind_host, port))
            return True
        except OSError:
            return False


class PlayitDownloader:
    """Downloads playit.gg agent binary from GitHub (no registration needed, uses ports 443/80)."""

    _GITHUB_API = "https://api.github.com/repos/playit-cloud/playit-agent/releases/latest"
    _ALLOWED_HOSTS = {"github.com", "objects.githubusercontent.com",
                      "github-releases.githubusercontent.com"}

    @staticmethod
    def get_dir() -> Path:
        if getattr(sys, "frozen", False):
            # Packaged exe is in Program Files (read-only); write binaries to LOCALAPPDATA
            local_app = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local")))
            base = local_app / "MCServer"
        else:
            base = Path(os.environ.get("APPDATA", str(Path.home()))) / "MCServer"
        base.mkdir(parents=True, exist_ok=True)
        return base

    @staticmethod
    def get_exe_path() -> Path:
        return PlayitDownloader.get_dir() / "playit.exe"

    @staticmethod
    def is_downloaded() -> bool:
        return PlayitDownloader.get_exe_path().is_file()

    @staticmethod
    def fetch_latest_windows_asset() -> tuple[str, str, str | None]:
        """Returns (exe_url, tag, sha256_url_or_None)."""
        req = urllib.request.Request(
            PlayitDownloader._GITHUB_API,
            headers={"User-Agent": "MCServer-App/1.0"},
        )
        with urllib.request.urlopen(req, timeout=15) as resp:  # nosec B310
            import json as _json
            data = _json.load(resp)
        tag: str = data.get("tag_name", "unknown")
        assets = data.get("assets", [])
        exe_url: str | None = None
        exe_name: str | None = None
        for asset in assets:
            name: str = asset.get("name", "")
            if "windows" in name.lower() and "x86_64" in name.lower() and name.endswith(".exe"):
                exe_url = asset["browser_download_url"]
                exe_name = name
                break
        if not exe_url or not exe_name:
            raise ValueError(f"No Windows x86_64 asset found in playit release {tag}")
        # Look for a matching checksum file alongside the exe
        sha_url: str | None = None
        candidates = {f"{exe_name}.sha256", "SHA256SUMS", "SHA256SUMS.txt", "checksums.txt"}
        for asset in assets:
            if asset.get("name", "") in candidates:
                sha_url = asset["browser_download_url"]
                break
        return exe_url, tag, sha_url

    @staticmethod
    def _verify_sha256(path: Path, sha_url: str, exe_name: str) -> None:
        """Download SHA-256 file and verify the downloaded binary."""
        parsed = urlparse(sha_url)
        if parsed.scheme != "https" or parsed.hostname not in PlayitDownloader._ALLOWED_HOSTS:
            return  # Untrusted checksum URL — skip rather than abort
        with urllib.request.urlopen(sha_url, timeout=15) as resp:  # nosec B310
            sha_text = resp.read().decode("utf-8", errors="replace")
        expected: str | None = None
        for line in sha_text.splitlines():
            parts = line.strip().split()
            # Formats: "HASH  filename" (sha256sum) or bare "HASH"
            if len(parts) >= 2 and parts[1].lstrip("*") == exe_name:
                expected = parts[0].lower()
                break
            if len(parts) == 1 and len(parts[0]) == 64:
                expected = parts[0].lower()
                break
        if expected is None:
            return  # Checksum file has no matching entry — skip
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        if h.hexdigest() != expected:
            raise ValueError(f"SHA-256 mismatch for downloaded playit.exe (got {h.hexdigest()[:12]}…)")

    @staticmethod
    def download(on_progress: Optional[Callable[[int, int], None]] = None) -> Path:
        url, _tag, sha_url = PlayitDownloader.fetch_latest_windows_asset()
        parsed = urlparse(url)
        if parsed.scheme != "https" or parsed.hostname not in PlayitDownloader._ALLOWED_HOSTS:
            raise ValueError("Refusing to download playit from untrusted URL")

        dest = PlayitDownloader.get_exe_path()
        tmp = PlayitDownloader.get_dir() / f".playit-{os.getpid()}.tmp"
        exe_name = url.rsplit("/", 1)[-1]
        try:
            with urllib.request.urlopen(url, timeout=300) as resp:  # nosec B310
                total = int(resp.headers.get("Content-Length", 0))
                done = 0
                with open(tmp, "wb") as f:
                    while True:
                        chunk = resp.read(65536)
                        if not chunk:
                            break
                        f.write(chunk)
                        done += len(chunk)
                        if on_progress:
                            on_progress(done, total)
                    f.flush()
                    os.fsync(f.fileno())
            if sha_url:
                PlayitDownloader._verify_sha256(tmp, sha_url, exe_name)
            if not PlayitDownloader._is_valid_pe(tmp):
                raise ValueError("Downloaded playit.exe is not a valid Windows executable")
            os.replace(tmp, dest)
        finally:
            try:
                tmp.unlink()
            except OSError:
                pass
        return dest

    @staticmethod
    def _is_valid_pe(path: Path) -> bool:
        try:
            with open(path, "rb") as f:
                header = f.read(64)
                if len(header) < 64 or header[:2] != b"MZ":
                    return False
                pe_offset = int.from_bytes(header[60:64], "little")
                if pe_offset <= 0:
                    return False
                f.seek(pe_offset)
                return f.read(4) == b"PE\0\0"
        except OSError:
            return False


class PlayitInstance:
    """Manages a running playit.gg agent process (guest mode — no account required)."""

    # Matches addresses like try.joinmc.link:25565 or abc.joinmc.link:12345
    _ADDR_RE = re.compile(
        r'([a-z0-9][a-z0-9.-]+\.(?:joinmc\.link|playit\.gg|ply\.gg):\d+)',
        re.IGNORECASE,
    )
    # Matches key=value address fields in structured playit logs
    _FIELD_ADDR_RE = re.compile(
        r'(?:addr|address|public|tunnel_addr|alloc_addr)=([^\s,\]]+\.\w{2,}:\d+)',
        re.IGNORECASE,
    )
    # Extracts TOML config path from startup log
    _SECRET_PATH_RE = re.compile(r'secret_path=Some\("([^"]+)"\)')
    _ANSI_RE = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    # Patterns for sensitive data that should not appear in the log panel
    _SANITIZE_RE = re.compile(
        r'(secret_path=Some\(")[^"]+(")'           # config file path
        r'|(agent_id=[0-9a-f\-]{8,})'              # agent UUID
        r'|(secret(?:_key)?=[A-Za-z0-9+/=_\-]{8,})',  # any secret= value
        re.IGNORECASE,
    )

    def __init__(self, port: int, on_output: Callable[[str, Optional[str]], None]):
        self.port = port
        self.on_output = on_output
        self.process: Optional[subprocess.Popen] = None
        self.stop_event = threading.Event()
        self.public_address: Optional[str] = None
        self._toml_path: Optional[str] = None

    def start(self) -> bool:
        exe = PlayitDownloader.get_exe_path()
        if not exe.is_file():
            self.on_output("playit.exe not found", None)
            return False
        try:
            self.stop_event.clear()
            flags = 0x08000000 if sys.platform == "win32" else 0  # CREATE_NO_WINDOW
            self.process = subprocess.Popen(  # nosec B603
                [str(exe)],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                creationflags=flags,
                errors="replace",
                bufsize=1,
                cwd=str(PlayitDownloader.get_dir()),
            )
            threading.Thread(target=self._read_loop, daemon=True).start()
            return True
        except Exception as e:
            self.on_output(f"Playit launch error: {e}", None)
            return False

    def stop(self):
        self.stop_event.set()
        if self.process:
            try:
                self.process.kill()
                self.process.wait(timeout=5)
            except (OSError, subprocess.TimeoutExpired):
                pass
            self.process = None
            self.public_address = None

    def _try_read_addr_from_toml(self) -> Optional[str]:
        """Read tunnel address from playit TOML config (Python 3.11+ tomllib)."""
        if not self._toml_path:
            # try standard locations
            for env, sub in (("LOCALAPPDATA", "playit_gg"), ("APPDATA", "playit_gg")):
                candidate = Path(os.environ.get(env, "")) / sub / "playit.toml"
                if candidate.is_file():
                    self._toml_path = str(candidate)
                    break
        if not self._toml_path:
            return None
        try:
            import tomllib  # stdlib since Python 3.11
            with open(self._toml_path, "rb") as f:
                cfg = tomllib.load(f)
            for tunnel in cfg.get("tunnels", []):
                # Look for domain / assigned address
                for key in ("domain", "custom_domain", "tunnel_address", "address"):
                    val = tunnel.get(key)
                    if val and isinstance(val, str) and "." in val:
                        port = tunnel.get("local_port") or tunnel.get("port") or self.port
                        return f"{val}:{port}"
        except Exception:  # nosec B110 — tomllib raises varied parse errors
            pass
        return None

    def _sanitize_line(self, line: str) -> str:
        def _mask(m: re.Match) -> str:
            if m.group(1):   # secret_path=Some("…")
                return m.group(1) + "[path hidden]" + m.group(2)
            if m.group(3):   # agent_id=…
                return "agent_id=[hidden]"
            return m.group(4).split("=")[0] + "=[hidden]"  # secret=…
        return self._SANITIZE_RE.sub(_mask, line)

    def _read_loop(self):
        if not self.process or not self.process.stdout:
            return
        for line in iter(self.process.stdout.readline, ""):
            if self.stop_event.is_set():
                break
            clean = self._ANSI_RE.sub("", line.strip())
            if not clean:
                continue
            clean = self._sanitize_line(clean)

            pub = None

            # 1. Extract TOML path from startup line
            sp = self._SECRET_PATH_RE.search(clean)
            if sp:
                self._toml_path = sp.group(1).replace("\\\\", "\\")

            # 2. Try regex on the log line
            if not self.public_address:
                m = self._ADDR_RE.search(clean)
                if not m:
                    m = self._FIELD_ADDR_RE.search(clean)
                if m:
                    addr = m.group(1)
                    # Skip loopback / LAN addresses
                    if not addr.startswith(("127.", "192.168.", "10.", "172.")):
                        self.public_address = addr
                        pub = addr

            # 3. When playit reports "connected", try reading TOML for address
            if not self.public_address and "playit connected" in clean.lower():
                addr = self._try_read_addr_from_toml()
                if addr:
                    self.public_address = addr
                    pub = addr

            self.on_output(clean, pub)

        if self.process and not self.stop_event.is_set():
            self.on_output("Playit process exited unexpectedly.", None)
        self.process = None
