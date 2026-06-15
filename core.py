import os
import sys
import json
import time
import shutil
import socket
import threading
import subprocess
import urllib.request
import re
import atexit
import tempfile
import uuid
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import Dict, Any, Optional, Callable, Tuple
from translations import _t, Translator

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
                            except: pass
    except Exception:
        return 0.0
    return total_size / (1024 * 1024 * 1024)

def strip_ansi_codes(text: str) -> str:
    """Removes ANSI escape sequences from text to make it readable and parsable."""
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    return ansi_escape.sub('', text)

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
        return ServerData(
            name=data.get('name', _t("CORE_TYPE_UNKNOWN")),
            core_name=data.get('core_name', ''),
            jar_path=data.get('jar_path', ''),
            ram=int(data.get('ram', 1024)),
            directory=data.get('directory', '')
        )

class ServerCallbacks:
    def __init__(self, 
                 on_log: Callable[[str, str], None], 
                 on_stats: Callable[[float, float, float, str, int, float, float, float], None], # 8 args
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
        # Stats
        self.start_time = None
        self.player_count = 0
        self.current_tps = 20.0
        self.core_type, self.version, self.supports_tps = parse_core_info(data.core_name)
        
    def set_state(self, new_state):
        self.state = new_state
        if self.callbacks.on_state:
            self.callbacks.on_state(new_state)

    def start(self):
        if self.state != ServerState.OFFLINE: return

        java_path = get_java_path()
        if not java_path:
            self.callbacks.on_log(_t("CORE_ERR_JAVA_NOT_FOUND"), "ERROR")
            self.callbacks.on_stop(-1)
            return

        eula_path = Path(self.data.directory) / "eula.txt"
        if not eula_path.exists():
            with open(eula_path, "w") as f: f.write("eula=true\n")

        self.start_time = time.time()
        self.player_count = 0
        self.current_tps = 20.0

        total_limit_mb = self.data.ram
        heap_mb = int(total_limit_mb * 0.75)
        if heap_mb < 512: heap_mb = 512

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

            self.process = subprocess.Popen(
                cmd,
                cwd=os.path.abspath(self.data.directory),
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                errors='replace',
                creationflags=creation_flags
            )

            if psutil:
                try: self.psutil_proc = psutil.Process(self.process.pid)
                except Exception: self.psutil_proc = None

            if sys.platform == 'win32':
                try: self._apply_windows_limit(total_limit_mb)
                except Exception: pass

            self.set_state(ServerState.STARTING)

            threading.Thread(target=self._log_reader_thread, daemon=True).start()
            threading.Thread(target=self._monitor_thread, daemon=True).start()

            self.callbacks.on_log(_t("CORE_LOG_SERVER_START", name=self.data.name), "INFO")

        except Exception as e:
            self.callbacks.on_log(_t("CORE_ERR_START_FAIL", error=e), "ERROR")
            self.callbacks.on_stop(-1)

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
        proc_handle = int(self.process._handle)
        ctypes.windll.kernel32.AssignProcessToJobObject(self.job_handle, proc_handle)

    def stop(self):
        if self.process and self.state in [ServerState.STARTING, ServerState.ONLINE]:
            self.set_state(ServerState.STOPPING)
            self.write_command("stop")
            self.callbacks.on_log(_t("CORE_LOG_STOP_SENT"), "WARN")

    def shutdown(self, timeout: float = 20.0) -> bool:
        """Gracefully stop the server, falling back to a forced kill."""
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
        if self.process:
            try:
                self.process.kill()
                self.process.wait(timeout=5)
            except Exception as e:
                if self.callbacks:
                    self.callbacks.on_log(_t("CORE_ERR_KILL", error=e), "WARN")
            self.process = None
        if self.job_handle:
            try:
                ctypes.windll.kernel32.CloseHandle(self.job_handle)
            except Exception:
                pass
            self.job_handle = None

    def write_command(self, command: str):
        if self.process and self.process.stdin:
            with self._stdin_lock:
                try:
                    self.process.stdin.write(command + "\n")
                    self.process.stdin.flush()
                except IOError:
                    pass

    def _log_reader_thread(self):
        if not self.process or not self.process.stdout: return
        
        done_pattern = re.compile(r'Done \((.+?)s\)!')
        ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
        
        join_regex = re.compile(r': (\w+) joined the game')
        leave_regex = re.compile(r': (\w+) left the game')

        for line in iter(self.process.stdout.readline, ''):
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
                except Exception: pass

            level = "INFO"
            if "WARN" in line: level = "WARN"
            elif "ERROR" in line or "Exception" in line: level = "ERROR"

            self.callbacks.on_log(line, level)

        exit_code = None
        if self.process:
            exit_code = self.process.wait()
        self.set_state(ServerState.OFFLINE)
        self.start_time = None
        self._stop_event.set()
        if self.job_handle:
            try:
                ctypes.windll.kernel32.CloseHandle(self.job_handle)
            except Exception:
                pass
            self.job_handle = None
        if exit_code is None and self.process:
            exit_code = self.process.returncode
        if exit_code is None:
            exit_code = -1
        self.callbacks.on_stop(exit_code)

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
                except: pass

            if self.state == ServerState.ONLINE and self.supports_tps and tick_counter % 8 == 0:
                self.write_command("tps")
            
            if tick_counter % 20 == 0:
                current_disk_gb = get_directory_size_gb(self.data.directory)

            tps_val = self.current_tps if self.supports_tps else -1.0
            
            # --- New Metrics ---
            mspt = 0.0
            if tps_val > 0:
                # Approximate MSPT: if 20 TPS, mspt <= 50.
                mspt = 50.0 + (20.0 - tps_val) * 10 if tps_val < 20 else 20.0 
            
            gc_time = 0.0 # Placeholder

            uptime_str = _t("CORE_UPTIME_ZERO")
            if self.start_time:
                delta = int(time.time() - self.start_time)
                h = delta // 3600
                m = (delta % 3600) // 60
                s = delta % 60
                uptime_str = _t("CORE_UPTIME_FMT", h=h, m=m, s=s)

            self.callbacks.on_stats(ram_mb, tps_val, current_disk_gb, uptime_str, self.player_count, cpu_percent, gc_time, mspt)
            
            time.sleep(0.5)
            tick_counter += 1

# --- PLAYIT MANAGER ---

class PlayitInstance:
    def __init__(self, exe_path: str, on_output: Callable[[str, Optional[str]], None]):
        self.exe_path = exe_path
        self.on_output = on_output
        self.process = None
        self.stop_event = threading.Event()
        self.public_address = None

    def start(self):
        if self.process: return
        try:
            self.stop_event.clear()
            creation_flags = 0
            if sys.platform == 'win32':
                creation_flags = CREATE_NO_WINDOW
            
            # IMPORTANT: Set CWD to the executable's directory
            work_dir = os.path.dirname(os.path.abspath(self.exe_path))
            
            self.process = subprocess.Popen(
                [self.exe_path],
                cwd=work_dir,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                creationflags=creation_flags,
                errors='replace',
                bufsize=1
            )
            threading.Thread(target=self._read_loop, daemon=True).start()
            return True
        except Exception as e:
            print(f"Playit launch error: {e}")
            if self.on_output:
                self.on_output(_t("CORE_PLAYIT_START_ERR", error=e), None)
            return False

    def stop(self):
        self.stop_event.set()
        if self.process:
            try: self.process.kill()
            except: pass
            self.process = None
            self.public_address = None

    def _read_loop(self):
        if not self.process or not self.process.stdout:
            return
        addr_regex = re.compile(r'(\S+\.playit\.gg(?::\d+)?)')
        for line in iter(self.process.stdout.readline, ''):
            if self.stop_event.is_set():
                break
            if not line:
                break
            clean_line = re.sub(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])', '', line.strip())
            match = addr_regex.search(clean_line)
            if match:
                self.public_address = match.group(1)
                if self.on_output:
                    self.on_output(clean_line, self.public_address)
            else:
                if self.on_output:
                    self.on_output(clean_line, None)
        if self.process and not self.stop_event.is_set():
            if self.on_output:
                self.on_output(_t("CORE_PLAYIT_EXITED"), None)
        self.process = None

# --- MANAGER ---

class ServerManager:
    def __init__(self, base_dir: str = "minecraft_servers"):
        self.servers_dir = Path(base_dir).resolve()
        self.servers_dir.mkdir(parents=True, exist_ok=True)
        self.config_file = self.servers_dir / "servers_config.json"
        self.settings_file = self.servers_dir / "app_settings.json"
        
        self.servers: Dict[str, ServerData] = self.load_servers()
        self.settings: Dict[str, Any] = self.load_settings()
        Translator().set_language(self.settings.get("language", "uk"))
        
        self.active_instance: Optional[ServerInstance] = None
        self.playit_instance: Optional[PlayitInstance] = None
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
        if self.playit_instance:
            self.playit_instance.stop()

    @staticmethod
    def _is_valid_server_name(name: str) -> bool:
        if not isinstance(name, str) or not name or name in {".", ".."}:
            return False
        if name != name.strip() or name.endswith((".", " ")):
            return False
        if any(ord(char) < 32 or char in '<>:"/\\|?*' for char in name):
            return False
        return True

    def _server_dir_for_name(self, name: str) -> Path:
        if not self._is_valid_server_name(name):
            raise ValueError("Invalid server name")
        path = (self.servers_dir / name).resolve()
        if path.parent != self.servers_dir:
            raise ValueError("Server path escapes the managed directory")
        return path

    def _managed_server_dir(self, server: ServerData) -> Path:
        path = Path(server.directory).resolve()
        if path.parent != self.servers_dir:
            raise ValueError("Server directory is outside the managed directory")
        return path

    @staticmethod
    def _atomic_write_json(path: Path, data: Any) -> None:
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

    def load_servers(self) -> Dict[str, ServerData]:
        if self.config_file.exists():
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return {name: ServerData.from_dict(info) for name, info in data.items()}
            except: return {}
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
                    settings.setdefault("playit_path", "")
                    settings.setdefault("language", "uk")
                    return settings
            except: pass
        return {"playit_path": "", "language": "uk"}

    def save_settings(self):
        self._atomic_write_json(self.settings_file, self.settings)

    def set_playit_path(self, path: str):
        self.settings["playit_path"] = path
        self.save_settings()

    def get_playit_path(self) -> str:
        return self.settings.get("playit_path", "")

    def set_language(self, lang_code: str):
        lang = "en" if lang_code == "en" else "uk"
        self.settings["language"] = lang
        self.save_settings()
        Translator().set_language(lang)

    def toggle_playit(self, on_output: Callable[[str, Optional[str]], None]) -> bool:
        """Returns True if started, False if stopped or failed"""
        if self.playit_instance and self.playit_instance.process:
            self.playit_instance.stop()
            self.playit_instance = None
            return False
        
        path = self.get_playit_path()
        if not path or not os.path.exists(path):
            return False
            
        self.playit_instance = PlayitInstance(path, on_output)
        success = self.playit_instance.start()
        if not success:
            self.playit_instance = None
            return False
        return True

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
            with open(s_dir / "start.bat", "w") as f:
                f.write(f'java -Xmx{ram_mb}M -Xms{ram_mb}M -jar "{jar_name}" nogui\npause')
            with open(s_dir / "eula.txt", "w") as f: f.write("eula=true\n")
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
        if not path.exists(): return {}
        props = {}
        with open(path, "r") as f:
            for line in f:
                if "=" in line and not line.strip().startswith("#"):
                    k, v = line.strip().split("=", 1)
                    props[k] = v
        return props

    def save_server_properties(self, server_name: str, new_props: Dict[str, str]):
        import tempfile
        server = self.servers.get(server_name)
        if not server:
            return
        path = Path(server.directory) / "server.properties"
        if not path.exists():
            return
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        tmp = path.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            for line in lines:
                if "=" in line and not line.strip().startswith("#"):
                    k = line.split("=", 1)[0].strip()
                    if k in new_props:
                        f.write(f"{k}={new_props[k]}\n")
                    else:
                        f.write(line)
                else:
                    f.write(line)
        tmp.replace(path)

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
            return urllib.request.urlopen('https://api.ipify.org', timeout=5).read().decode('utf8')
        except Exception:
            return _t("CORE_UNAVAILABLE")
