import os
import sys
import json
import time
import shutil
import threading
import subprocess  # nosec B404
import tempfile
import urllib.request
import re
import atexit
import uuid
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import Dict, Any, Optional, Callable, Tuple
from translations import _t, Translator
from services import AtomicJsonStore, PlayitDownloader, PlayitInstance, NetworkService, ServerPathPolicy

try:
    import psutil
except ImportError:
    psutil = None

# --- JAVA PATH HELPER ---
def get_java_path() -> Optional[str]:
    """Повертає шлях до вбудованої JRE або системної Java."""
    # sys.frozen встановлюється PyInstaller при запуску exe
    if getattr(sys, 'frozen', False):
        base = Path(sys.executable).parent
        bundled = base / "jre" / "bin" / "java.exe"
        if bundled.exists():
            return str(bundled)
    # Fallback на системну
    java = shutil.which('java')
    if java:
        return java
    return None

# --- WINDOWS HARD LIMITS (JOB OBJECTS) ---
if sys.platform == 'win32':
    import ctypes
    from ctypes import wintypes

    class IO_COUNTERS(ctypes.Structure):
        _fields_ = [('ReadOperationCount', ctypes.c_ulonglong),
                    ('WriteOperationCount', ctypes.c_ulonglong),
                    ('OtherOperationCount', ctypes.c_ulonglong),
                    ('ReadTransferCount', ctypes.c_ulonglong),
                    ('WriteTransferCount', ctypes.c_ulonglong),
                    ('OtherTransferCount', ctypes.c_ulonglong)]

    class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
        _fields_ = [('PerProcessUserTimeLimit', ctypes.c_longlong),
                    ('PerJobUserTimeLimit', ctypes.c_longlong),
                    ('LimitFlags', ctypes.c_ulong),
                    ('MinimumWorkingSetSize', ctypes.c_size_t),
                    ('MaximumWorkingSetSize', ctypes.c_size_t),
                    ('ActiveProcessLimit', ctypes.c_ulong),
                    ('Affinity', ctypes.c_ulong),
                    ('PriorityClass', ctypes.c_ulong),
                    ('SchedulingClass', ctypes.c_ulong)]

    class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
        _fields_ = [('BasicLimitInformation', JOBOBJECT_BASIC_LIMIT_INFORMATION),
                    ('IoInfo', IO_COUNTERS),
                    ('ProcessMemoryLimit', ctypes.c_size_t),
                    ('JobMemoryLimit', ctypes.c_size_t),
                    ('PeakProcessMemoryUsed', ctypes.c_size_t),
                    ('PeakJobMemoryUsed', ctypes.c_size_t)]

    JOB_OBJECT_LIMIT_PROCESS_MEMORY = 0x00000100
    JobObjectExtendedLimitInformation = 9
    CREATE_NO_WINDOW = 0x08000000
    CREATE_BREAKAWAY_FROM_JOB = 0x01000000

# --- CONSTANTS ---
class ServerState:
    OFFLINE = "OFFLINE"
    STARTING = "STARTING"
    ONLINE = "ONLINE"
    STOPPING = "STOPPING"

# --- HELPERS ---
def parse_core_info(jar_name: str) -> Tuple[str, str, bool]:
    jar_lower = jar_name.lower()
    version = _t("CORE_TYPE_UNKNOWN")
    v_match = re.search(r"(\d+\.\d+(\.\d+)?)", jar_name)
    if v_match:
        version = v_match.group(1)

    if 'paper' in jar_lower: return _t("CORE_TYPE_PAPER"), version, True
    if 'purpur' in jar_lower: return _t("CORE_TYPE_PURPUR"), version, True
    if 'spigot' in jar_lower: return _t("CORE_TYPE_SPIGOT"), version, False
    if 'bukkit' in jar_lower: return _t("CORE_TYPE_BUKKIT"), version, False
    if 'fabric' in jar_lower: return _t("CORE_TYPE_FABRIC"), version, False
    if 'forge' in jar_lower: return _t("CORE_TYPE_FORGE"), version, False
    if 'vanilla' in jar_lower or 'server' in jar_lower: return _t("CORE_TYPE_VANILLA"), version, False

    return _t("CORE_TYPE_UNKNOWN"), version, False

def get_directory_size_gb(start_path: str) -> float:
    total_size = 0
    try:
        with os.scandir(start_path) as it:
            for entry in it:
                if entry.is_file():
                    total_size += entry.stat().st_size
                elif entry.is_dir():
                    for dirpath, _, filenames in os.walk(entry.path):
                        for f in filenames:
                            fp = os.path.join(dirpath, f)
                            try: total_size += os.path.getsize(fp)
                            except OSError: pass
    except Exception:
        return 0.0
    return total_size / (1024 * 1024 * 1024)

def strip_ansi_codes(text: str) -> str:
    """Removes ANSI escape sequences from text to make it readable and parsable."""
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    return ansi_escape.sub('', text)


def read_properties_file(path: Path) -> Dict[str, str]:
    if not path.exists():
        return {}
    props = {}
    try:
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            # server.properties files created on non-UTF-8 systems use latin-1
            text = path.read_text(encoding="latin-1")
        for line in text.splitlines():
            if "=" in line and not line.strip().startswith("#"):
                key, value = line.strip().split("=", 1)
                props[key] = value
    except OSError:
        return {}
    return props

# --- DATA STRUCTURES ---

@dataclass
class ServerData:
    name: str
    core_name: str
    jar_path: str
    ram: int
    directory: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @staticmethod
    def from_dict(data: Dict[str, Any]) -> 'ServerData':
        try:
            ram = int(data.get('ram', 1024))
        except (TypeError, ValueError):
            ram = 1024
        ram = min(max(ram, 512), 262144)
        return ServerData(
            name=data.get('name', _t("CORE_TYPE_UNKNOWN")),
            core_name=data.get('core_name', ''),
            jar_path=data.get('jar_path', ''),
            ram=ram,
            directory=data.get('directory', '')
        )

class ServerCallbacks:
    def __init__(self, 
                 on_log: Callable[[str, str], None], 
                 on_stats: Callable[[float, float, float, str, int, float], None],  # ram, tps, disk, uptime, players, cpu
                 on_state: Callable[[str], None],
                 on_stop: Callable[[int], None]):
        self.on_log = on_log
        self.on_stats = on_stats
        self.on_state = on_state
        self.on_stop = on_stop

# --- ACTIVE SERVER INSTANCE ---

class ServerInstance:
    def __init__(self, data: ServerData, callbacks: ServerCallbacks):
        self.data = data
        self.callbacks = callbacks
        self.process: Optional[subprocess.Popen] = None
        self.psutil_proc = None
        self.state = ServerState.OFFLINE
        self._stop_event = threading.Event()
        self.job_handle = None
        self._stdin_lock = threading.Lock()
        self._lifecycle_lock = threading.RLock()
        self._stop_reported = False
        # Stats
        self.start_time: Optional[float] = None
        self.player_count = 0
        self.current_tps = 20.0
        self.core_type, self.version, self.supports_tps = parse_core_info(data.core_name)
        
    @staticmethod
    def needs_eula(server_dir: str) -> bool:
        """Returns True if the server directory still requires EULA acceptance."""
        eula_path = Path(server_dir) / "eula.txt"
        if not eula_path.exists():
            return True
        try:
            return "eula=true" not in eula_path.read_text(encoding="utf-8").lower()
        except OSError:
            return True

    @staticmethod
    def write_eula(server_dir: str) -> None:
        """Writes eula=true to the server directory after explicit user consent."""
        with open(Path(server_dir) / "eula.txt", "w", encoding="utf-8") as f:
            f.write("eula=true\n")

    def set_state(self, new_state):
        with self._lifecycle_lock:
            self.state = new_state
        self.callbacks.on_state(new_state)

    def _abort_start(self) -> None:
        """Reset state to OFFLINE after a failed start attempt."""
        with self._lifecycle_lock:
            self.state = ServerState.OFFLINE
        self.callbacks.on_state(ServerState.OFFLINE)

    def _report_stop_once(self, exit_code: int) -> None:
        with self._lifecycle_lock:
            if self._stop_reported:
                return
            self._stop_reported = True
        self.callbacks.on_stop(exit_code)

    def _preflight_start(self) -> bool:
        server_dir = Path(self.data.directory)
        if not server_dir.is_dir():
            self.callbacks.on_log(f"Server directory is missing: {server_dir}", "ERROR")
            self._report_stop_once(-1)
            return False
        jar_path = server_dir / self.data.core_name
        if not jar_path.is_file():
            self.callbacks.on_log(f"Server jar is missing: {jar_path}", "ERROR")
            self._report_stop_once(-1)
            return False
        try:
            with open(jar_path, "rb"):
                pass
        except OSError as error:
            self.callbacks.on_log(f"Server jar is not readable: {error}", "ERROR")
            self._report_stop_once(-1)
            return False
        return True

    def start(self):
        with self._lifecycle_lock:
            if self.state != ServerState.OFFLINE:
                return
            self._stop_event.clear()
            self._stop_reported = False
            # Set STARTING under lock immediately to block concurrent start() calls
            self.state = ServerState.STARTING
        self.callbacks.on_state(ServerState.STARTING)

        if not self._preflight_start():
            self._abort_start()
            return

        java_path = get_java_path()
        if not java_path:
            self.callbacks.on_log(_t("CORE_ERR_JAVA_NOT_FOUND"), "ERROR")
            self._report_stop_once(-1)
            self._abort_start()
            return

        properties = read_properties_file(Path(self.data.directory) / "server.properties")
        try:
            port = int(properties.get("server-port", "25565"))
            if not (1 <= port <= 65535):
                raise ValueError(f"Port {port} is outside the valid range 1–65535")
        except ValueError as exc:
            self.callbacks.on_log(_t("CORE_ERR_PORT_INVALID", error=exc), "ERROR")
            self._report_stop_once(-1)
            self._abort_start()
            return
        host = properties.get("server-ip", "")
        if not NetworkService.is_port_available(host, port):
            self.callbacks.on_log(_t("CORE_ERR_PORT_BUSY", port=port), "ERROR")
            self._report_stop_once(-1)
            self._abort_start()
            return

        self.start_time = time.time()
        self.player_count = 0
        self.current_tps = 20.0

        heap_mb = self.data.ram
        if heap_mb < 512: heap_mb = 512
        total_limit_mb = heap_mb + 512

        cmd = [
            java_path,
            f'-Xmx{heap_mb}M',
            f'-Xms{heap_mb}M',
            '-jar', self.data.core_name,
            'nogui'
        ]

        try:
            creation_flags = 0
            if sys.platform == 'win32':
                creation_flags = CREATE_NO_WINDOW | CREATE_BREAKAWAY_FROM_JOB

            process = subprocess.Popen(  # nosec B603
                cmd,
                cwd=os.path.abspath(self.data.directory),
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                errors='replace',
                creationflags=creation_flags
            )
            with self._lifecycle_lock:
                self.process = process

            if psutil:
                try: self.psutil_proc = psutil.Process(process.pid)
                except Exception as error:
                    self.psutil_proc = None
                    self.callbacks.on_log(f"Process stats unavailable: {error}", "WARN")

            if sys.platform == 'win32':
                try: self._apply_windows_limit(total_limit_mb)
                except Exception as error:
                    self.callbacks.on_log(f"RAM limit could not be applied: {error}", "WARN")

            # State is already STARTING (set under lock above); threads take over from here
            threading.Thread(target=self._log_reader_thread, daemon=True).start()
            threading.Thread(target=self._monitor_thread, daemon=True).start()

            self.callbacks.on_log(_t("CORE_LOG_SERVER_START", name=self.data.name), "INFO")

        except Exception as e:
            self.callbacks.on_log(_t("CORE_ERR_START_FAIL", error=e), "ERROR")
            with self._lifecycle_lock:
                self.process = None
            self._report_stop_once(-1)
            self._abort_start()

    def _apply_windows_limit(self, limit_mb):
        if self.job_handle:
            return
        self.job_handle = ctypes.windll.kernel32.CreateJobObjectW(None, None)
        if not self.job_handle: return

        info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
        info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_PROCESS_MEMORY
        info.ProcessMemoryLimit = int(limit_mb * 1024 * 1024)

        ctypes.windll.kernel32.SetInformationJobObject(
            self.job_handle, JobObjectExtendedLimitInformation,
            ctypes.byref(info), ctypes.sizeof(JOBOBJECT_EXTENDED_LIMIT_INFORMATION)
        )
        if not self.process:
            return
        proc_handle = int(self.process._handle)
        ctypes.windll.kernel32.AssignProcessToJobObject(self.job_handle, proc_handle)

    def stop(self):
        if self.process and self.state in [ServerState.STARTING, ServerState.ONLINE]:
            self.set_state(ServerState.STOPPING)
            self.write_command("stop")
            self.callbacks.on_log(_t("CORE_LOG_STOP_SENT"), "WARN")

    def shutdown(self, timeout: float = 20.0) -> bool:
        """Gracefully stop the server, falling back to a forced kill."""
        with self._lifecycle_lock:
            process = self.process
        if not process or process.poll() is not None:
            return True

        self.stop()
        try:
            process.wait(timeout=timeout)
            return True
        except subprocess.TimeoutExpired:
            self.kill()
            return False

    def kill(self):
        with self._lifecycle_lock:
            process = self.process
        if process:
            try:
                process.kill()
                process.wait(timeout=5)
            except Exception as e:
                if self.callbacks:
                    self.callbacks.on_log(_t("CORE_ERR_KILL", error=e), "WARN")
            with self._lifecycle_lock:
                if self.process is process:
                    self.process = None
        if self.job_handle:
            try:
                ctypes.windll.kernel32.CloseHandle(self.job_handle)
            except Exception:  # nosec B110 — ctypes raises opaque OSError variants
                pass
            self.job_handle = None

    def write_command(self, command: str):
        with self._lifecycle_lock:
            process = self.process
        if process and process.stdin:
            with self._stdin_lock:
                try:
                    process.stdin.write(command + "\n")
                    process.stdin.flush()
                except (BrokenPipeError, OSError, ValueError) as error:
                    self.callbacks.on_log(f"Command could not be sent: {error}", "WARN")

    def _log_reader_thread(self):
        with self._lifecycle_lock:
            process = self.process
        if not process or not process.stdout: return
        
        done_pattern = re.compile(r'Done \((.+?)s\)!')
        ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
        
        join_regex = re.compile(r': (\w+) joined the game')
        leave_regex = re.compile(r': (\w+) left the game')

        for line in iter(process.stdout.readline, ''):
            if not line: break
            clean_line = ansi_escape.sub('', line)

            if self.state == ServerState.STARTING:
                if done_pattern.search(line):
                    self.set_state(ServerState.ONLINE)

            if JOIN_REGEX := join_regex.search(clean_line):
                self.player_count += 1
            elif LEAVE_REGEX := leave_regex.search(clean_line):
                self.player_count = max(0, self.player_count - 1)

            if self.supports_tps and "TPS" in clean_line:
                try:
                    match = re.search(r'TPS.*?:.*?(\d+(?:[.,]\d+)?)', clean_line)
                    if match:
                        tps_str = match.group(1).replace(',', '.')
                        self.current_tps = min(float(tps_str), 20.0)
                except (TypeError, ValueError) as error:
                    self.callbacks.on_log(f"Could not parse TPS output: {error}", "WARN")

            level = "INFO"
            if "WARN" in line: level = "WARN"
            elif "ERROR" in line or "Exception" in line: level = "ERROR"

            self.callbacks.on_log(line, level)

        exit_code = None
        try:
            exit_code = process.wait()
        except OSError:
            exit_code = process.returncode
        self.set_state(ServerState.OFFLINE)
        self.start_time = None
        self._stop_event.set()
        if self.job_handle:
            try:
                ctypes.windll.kernel32.CloseHandle(self.job_handle)
            except Exception:  # nosec B110
                pass
            self.job_handle = None
        with self._lifecycle_lock:
            if self.process is process:
                self.process = None
        if exit_code is None:
            exit_code = process.returncode
        if exit_code is None:
            exit_code = -1
        self._report_stop_once(exit_code)

    # Maximum time (seconds) a server may stay in STARTING before we kill it
    _STARTING_TIMEOUT = 600

    def _monitor_thread(self):
        tick_counter = 0
        current_disk_gb = get_directory_size_gb(self.data.directory)

        while self.state != ServerState.OFFLINE and not self._stop_event.is_set():
            ram_mb = 0.0
            cpu_percent = 0.0

            if self.psutil_proc:
                try:
                    mem = self.psutil_proc.memory_info()
                    total_bytes = mem.rss
                    for child in self.psutil_proc.children(recursive=True):
                        total_bytes += child.memory_info().rss
                    ram_mb = total_bytes / 1024 / 1024
                    cpu_percent = self.psutil_proc.cpu_percent()
                except (psutil.Error, OSError, RuntimeError) if psutil else (OSError, RuntimeError):
                    ram_mb = 0.0
                    cpu_percent = 0.0

            # STARTING timeout: kill if "Done (…)!" never arrives within the window
            if self.state == ServerState.STARTING and self.start_time:
                elapsed = time.time() - self.start_time
                if elapsed > self._STARTING_TIMEOUT:
                    self.callbacks.on_log(_t("CORE_ERR_STARTING_TIMEOUT"), "ERROR")
                    self.kill()

            if self.state == ServerState.ONLINE and self.supports_tps and tick_counter % 8 == 0:
                self.write_command("tps")

            # Full directory walk is expensive on large worlds — scan every 5 minutes
            if tick_counter % 300 == 0:
                current_disk_gb = get_directory_size_gb(self.data.directory)

            tps_val = self.current_tps if self.supports_tps else -1.0

            uptime_str = _t("CORE_UPTIME_ZERO")
            if self.start_time:
                delta = int(time.time() - self.start_time)
                h = delta // 3600
                m = (delta % 3600) // 60
                s = delta % 60
                uptime_str = _t("CORE_UPTIME_FMT", h=h, m=m, s=s)

            self.callbacks.on_stats(ram_mb, tps_val, current_disk_gb, uptime_str, self.player_count, cpu_percent)
            
            time.sleep(1.0)
            tick_counter += 1


# --- MANAGER ---

class ServerManager:
    def __init__(self, base_dir: str | None = None):
        if base_dir is None:
            if getattr(sys, "frozen", False):
                # Packaged exe → store user data in %LOCALAPPDATA%\MCServer\servers
                local_app = Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local")))
                base_dir = str(local_app / "MCServer" / "servers")
            else:
                base_dir = "minecraft_servers"
        self.servers_dir = Path(base_dir).resolve()
        self.servers_dir.mkdir(parents=True, exist_ok=True)
        self.path_policy = ServerPathPolicy(self.servers_dir)
        self.config_file = self.servers_dir / "servers_config.json"
        self.settings_file = self.servers_dir / "app_settings.json"
        self.last_config_error = ""
        
        self.servers: Dict[str, ServerData] = self.load_servers()
        self.settings: Dict[str, Any] = self.load_settings()
        Translator().set_language(self.settings.get("language", "uk"))
        
        self.active_instance: Optional[ServerInstance] = None
        self.tunnel_instance: Optional[PlayitInstance] = None
        self._cleanup_lock = threading.Lock()
        self._cleaned_up = False
        
        atexit.register(self.cleanup)

    def cleanup(self):
        with self._cleanup_lock:
            if self._cleaned_up:
                return
            self._cleaned_up = True

        if (
            self.active_instance
            and self.active_instance.process
            and self.active_instance.process.poll() is None
        ):
            self.active_instance.shutdown()
        if self.tunnel_instance:
            self.tunnel_instance.stop()

    @staticmethod
    def _is_valid_server_name(name: str) -> bool:
        return ServerPathPolicy.is_valid_name(name)

    def _server_dir_for_name(self, name: str) -> Path:
        return self.path_policy.directory_for_name(name)

    def _managed_server_dir(self, server: ServerData) -> Path:
        return self.path_policy.require_managed_directory(server.directory)

    @staticmethod
    def _atomic_write_json(path: Path, data: Any) -> None:
        AtomicJsonStore.write(path, data)

    def load_servers(self) -> Dict[str, ServerData]:
        if self.config_file.exists():
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                if not isinstance(data, dict):
                    raise ValueError("servers_config.json must contain an object")
                servers = {}
                bad_names: list = []
                for name, info in data.items():
                    if not isinstance(info, dict) or not self._is_valid_server_name(name):
                        bad_names.append(name)
                        continue  # Skip corrupt entries; keep valid ones
                    server = ServerData.from_dict(info)
                    server.name = name
                    # Reject entries whose stored directory escapes the managed tree
                    try:
                        self.path_policy.require_managed_directory(server.directory)
                    except ValueError:
                        bad_names.append(name)
                        continue
                    servers[name] = server
                if bad_names:
                    self.last_config_error = f"Skipped {len(bad_names)} invalid entries: {bad_names}"
                return servers
            except (OSError, json.JSONDecodeError, TypeError, ValueError) as error:
                self.last_config_error = str(error)
                self._backup_corrupt_file(self.config_file)
                return {}
        return {}

    def save_servers(self) -> None:
        self._atomic_write_json(
            self.config_file,
            {name: server.to_dict() for name, server in self.servers.items()},
        )

    def load_settings(self) -> Dict[str, Any]:
        if self.settings_file.exists():
            try:
                with open(self.settings_file, 'r', encoding='utf-8') as f:
                    settings = json.load(f)
                    if not isinstance(settings, dict):
                        raise ValueError("app_settings.json must contain an object")
                    settings.setdefault("language", "uk")
                    return settings
            except (OSError, json.JSONDecodeError, TypeError, ValueError) as error:
                self.last_config_error = str(error)
                self._backup_corrupt_file(self.settings_file)
        return {"language": "uk"}

    @staticmethod
    def _backup_corrupt_file(path: Path) -> None:
        try:
            if path.exists():
                backup = path.with_suffix(path.suffix + f".corrupt-{int(time.time())}.bak")
                path.replace(backup)
        except OSError:
            pass

    def save_settings(self):
        self._atomic_write_json(self.settings_file, self.settings)

    def set_language(self, lang_code: str):
        lang = "en" if lang_code == "en" else "uk"
        self.settings["language"] = lang
        self.save_settings()
        Translator().set_language(lang)

    def toggle_tunnel(self, port: int, on_output: Callable[[str, Optional[str]], None]) -> bool:
        """Start or stop the playit tunnel. Returns True if started, False if stopped/failed."""
        if self.tunnel_instance and self.tunnel_instance.process:
            self.tunnel_instance.stop()
            self.tunnel_instance = None
            return False
        self.tunnel_instance = PlayitInstance(port, on_output)
        ok = self.tunnel_instance.start()
        if not ok:
            self.tunnel_instance = None
        return ok

    def create_server(self, name: str, jar_source: str, ram_mb: int) -> bool:
        if name in self.servers:
            return False
        try:
            s_dir = self._server_dir_for_name(name)
            jar_path = Path(jar_source)
            if s_dir.exists() or not jar_path.is_file() or jar_path.suffix.lower() != ".jar":
                return False
            s_dir.mkdir()
            jar_name = jar_path.name
            shutil.copy2(jar_source, s_dir / jar_name)
            with open(s_dir / "start.bat", "w", encoding="utf-8") as f:
                f.write(f'java -Xmx{ram_mb}M -Xms{ram_mb}M -jar "{jar_name}" nogui\npause')
            # eula.txt is NOT pre-written here; the EULA dialog in dashboard.on_start() handles consent
            new_server = ServerData(name, jar_name, str(s_dir / jar_name), ram_mb, str(s_dir))
            self.servers[name] = new_server
            try:
                self.save_servers()
            except Exception:
                self.servers.pop(name, None)
                raise
            return True
        except Exception:
            if 's_dir' in locals() and s_dir.exists():
                shutil.rmtree(s_dir, ignore_errors=True)
            return False

    def delete_server(self, name: str) -> bool:
        if name not in self.servers:
            return False
        if self.active_instance and self.active_instance.data.name == name and self.active_instance.state != ServerState.OFFLINE:
            return False

        server = self.servers[name]
        trash_dir = None
        try:
            server_dir = self._managed_server_dir(server)
            if server_dir.exists():
                trash_root = self.servers_dir / ".trash"
                trash_root.mkdir(exist_ok=True)
                trash_dir = trash_root / f"{server_dir.name}-{uuid.uuid4().hex}"
                server_dir.rename(trash_dir)

            self.servers.pop(name)
            try:
                self.save_servers()
            except Exception:
                self.servers[name] = server
                if trash_dir and trash_dir.exists():
                    trash_dir.rename(server_dir)
                raise

            if trash_dir and trash_dir.exists():
                shutil.rmtree(trash_dir)
            return True
        except Exception:
            if trash_dir and trash_dir.exists() and 'server_dir' in locals() and not server_dir.exists():
                try:
                    trash_dir.rename(server_dir)
                    self.servers[name] = server
                    self.save_servers()
                except Exception:  # nosec B110 — last-resort rollback, nothing more to do
                    pass
            return False

    def rename_server(self, old_name: str, new_name: str) -> bool:
        if new_name in self.servers or old_name not in self.servers:
            return False
        server = self.servers.pop(old_name)
        old_server_data = ServerData.from_dict(server.to_dict())
        old_dir = None
        new_dir = None
        try:
            old_dir = self._managed_server_dir(server)
            new_dir = self._server_dir_for_name(new_name)
            if new_dir.exists():
                raise OSError("Target server directory already exists")
            if old_dir.exists():
                old_dir.rename(new_dir)
            server.name = new_name
            server.directory = str(new_dir)
            if server.jar_path:
                server.jar_path = str(new_dir / Path(server.jar_path).name)
        except (OSError, ValueError):
            self.servers[old_name] = server  # rollback
            return False
        self.servers[new_name] = server
        try:
            self.save_servers()
            return True
        except Exception:
            self.servers.pop(new_name, None)
            self.servers[old_name] = old_server_data
            if old_dir and new_dir and new_dir.exists() and not old_dir.exists():
                try:
                    new_dir.rename(old_dir)
                except OSError:
                    pass
            return False

    def start_instance(self, server_name: str, callbacks: ServerCallbacks):
        if self.active_instance and self.active_instance.state != ServerState.OFFLINE: return 
        if server_name not in self.servers: return
        self.active_instance = ServerInstance(self.servers[server_name], callbacks)
        self.active_instance.start()

    def stop_instance(self):
        if self.active_instance: self.active_instance.stop()

    def kill_instance(self):
        if self.active_instance: self.active_instance.kill()

    def send_command(self, cmd: str):
        if self.active_instance and self.active_instance.state != ServerState.OFFLINE:
            self.active_instance.write_command(cmd)

    def get_server_properties(self, server_name: str) -> Dict[str, str]:
        server = self.servers.get(server_name)
        if not server: return {}
        path = Path(server.directory) / "server.properties"
        return read_properties_file(path)

    def save_server_properties(self, server_name: str, new_props: Dict[str, str]):
        server = self.servers.get(server_name)
        if not server:
            return
        path = Path(server.directory) / "server.properties"
        if not path.exists():
            return
        # Detect encoding to match what the server originally wrote (mirrors read_properties_file)
        try:
            lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
            enc = "utf-8"
        except UnicodeDecodeError:
            lines = path.read_text(encoding="latin-1").splitlines(keepends=True)
            enc = "latin-1"
        # Strip newline/control chars from values to prevent line injection
        clean = {k: re.sub(r'[\r\n]', '', v) for k, v in new_props.items()}
        tmp = None
        try:
            with tempfile.NamedTemporaryFile("w", encoding=enc, dir=path.parent, delete=False, suffix=".tmp") as f:
                tmp = Path(f.name)
                for line in lines:
                    if "=" in line and not line.strip().startswith("#"):
                        k = line.split("=", 1)[0].strip()
                        if k in clean:
                            f.write(f"{k}={clean[k]}\n")
                        else:
                            f.write(line)
                    else:
                        f.write(line)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, path)
        finally:
            if tmp and tmp.exists():
                try:
                    tmp.unlink()
                except OSError:
                    pass

    @staticmethod
    def get_dir_size_gb(path: str) -> float:
        return get_directory_size_gb(path)

    @staticmethod
    def get_local_ip() -> str:
        import socket
        try:
            return socket.gethostbyname(socket.gethostname())
        except Exception:
            return "127.0.0.1"

    @staticmethod
    def get_public_ip() -> str:
        import urllib.request
        try:
            return urllib.request.urlopen('https://api.ipify.org', timeout=5).read().decode('utf8')  # nosec B310
        except Exception:
            return _t("CORE_UNAVAILABLE")
