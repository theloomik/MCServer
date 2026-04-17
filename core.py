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
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import Dict, Any, Optional, Callable, Tuple

try:
    import psutil
except ImportError:
    psutil = None

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
    version = "Unknown"
    v_match = re.search(r"(\d+\.\d+(\.\d+)?)", jar_name)
    if v_match:
        version = v_match.group(1)

    if 'paper' in jar_lower: return "Paper", version, True
    if 'purpur' in jar_lower: return "Purpur", version, True
    if 'spigot' in jar_lower: return "Spigot", version, False
    if 'bukkit' in jar_lower: return "Bukkit", version, False
    if 'fabric' in jar_lower: return "Fabric", version, False
    if 'forge' in jar_lower: return "Forge", version, False
    if 'vanilla' in jar_lower or 'server' in jar_lower: return "Vanilla", version, False

    return "Unknown", version, False

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
            name=data.get('name', 'Unknown'),
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

        java_path = shutil.which('java')
        if not java_path:
            self.callbacks.on_log("ERROR: Java not found!\n", "ERROR")
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
            'java',
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
                except: self.psutil_proc = None
            
            if sys.platform == 'win32':
                try: self._apply_windows_limit(total_limit_mb)
                except Exception: pass

            self.set_state(ServerState.STARTING)
            
            threading.Thread(target=self._log_reader_thread, daemon=True).start()
            threading.Thread(target=self._monitor_thread, daemon=True).start()
            
            self.callbacks.on_log(f"--- Запуск сервера: {self.data.name} ---\n", "INFO")

        except Exception as e:
            self.callbacks.on_log(f"Failed to start: {e}\n", "ERROR")
            self.callbacks.on_stop(-1)

    def _apply_windows_limit(self, limit_mb):
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
            self.callbacks.on_log("--- Stop command sent ---\n", "WARN")

    def kill(self):
        if self.process: 
            try: self.process.kill()
            except: pass
        if self.job_handle:
            ctypes.windll.kernel32.CloseHandle(self.job_handle)
            self.job_handle = None

    def write_command(self, command: str):
        if self.process and self.process.stdin:
            try:
                self.process.stdin.write(command + "\n")
                self.process.stdin.flush()
            except IOError: pass

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

        self.process.wait()
        self.set_state(ServerState.OFFLINE)
        self.start_time = None
        self._stop_event.set()
        
        if self.job_handle:
            ctypes.windll.kernel32.CloseHandle(self.job_handle)
            self.job_handle = None
            
        self.callbacks.on_stop(self.process.returncode)

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

            uptime_str = "0 год 0 хв 0 с"
            if self.start_time:
                delta = int(time.time() - self.start_time)
                h = delta // 3600
                m = (delta % 3600) // 60
                s = delta % 60
                uptime_str = f"{h} год {m} хв {s} с"

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
                errors='replace'
            )
            threading.Thread(target=self._read_loop, daemon=True).start()
            return True
        except Exception as e:
            print(f"Playit launch error: {e}")
            if self.on_output:
                self.on_output(f"Error starting playit: {e}", None)
            return False

    def stop(self):
        self.stop_event.set()
        if self.process:
            try: self.process.kill()
            except: pass
            self.process = None
            self.public_address = None

    def _read_loop(self):
        # Improved Regex: matches playit.gg domains
        addr_regex = re.compile(r'(\S+\.playit\.gg(?::\d+)?)') 
        
        while self.process and not self.stop_event.is_set():
            line = self.process.stdout.readline()
            if not line: break
            
            # CRITICAL FIX: Clean ANSI codes (colors, cursor movements) from the line
            clean_line = strip_ansi_codes(line.strip())
            
            # Try to grab the address from CLEAN text
            if not self.public_address:
                if match := addr_regex.search(clean_line):
                    found = match.group(1)
                    # Simple filter to avoid grabbing urls like https://playit.gg/claim...
                    if "https" not in found and "http" not in found:
                         self.public_address = found
            
            # Pass CLEAN text to UI
            if self.on_output:
                self.on_output(clean_line, self.public_address)
        
        self.process = None

# --- MANAGER ---

class ServerManager:
    def __init__(self, base_dir: str = "minecraft_servers"):
        self.servers_dir = Path(base_dir)
        self.servers_dir.mkdir(exist_ok=True)
        self.config_file = self.servers_dir / "servers_config.json"
        self.settings_file = self.servers_dir / "app_settings.json"
        
        self.servers: Dict[str, ServerData] = self.load_servers()
        self.settings: Dict[str, Any] = self.load_settings()
        
        self.active_instance: Optional[ServerInstance] = None
        self.playit_instance: Optional[PlayitInstance] = None
        
        atexit.register(self.cleanup)

    def cleanup(self):
        if self.active_instance and self.active_instance.state != ServerState.OFFLINE:
            self.active_instance.kill()
        if self.playit_instance:
            self.playit_instance.stop()

    def load_servers(self) -> Dict[str, ServerData]:
        if self.config_file.exists():
            try:
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return {name: ServerData.from_dict(info) for name, info in data.items()}
            except: return {}
        return {}

    def save_servers(self) -> None:
        with open(self.config_file, 'w', encoding='utf-8') as f:
            json.dump({name: s.to_dict() for name, s in self.servers.items()}, f, indent=2, ensure_ascii=False)

    def load_settings(self) -> Dict[str, Any]:
        if self.settings_file.exists():
            try:
                with open(self.settings_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except: pass
        return {"playit_path": ""}

    def save_settings(self):
        with open(self.settings_file, 'w', encoding='utf-8') as f:
            json.dump(self.settings, f, indent=2, ensure_ascii=False)

    def set_playit_path(self, path: str):
        self.settings["playit_path"] = path
        self.save_settings()

    def get_playit_path(self) -> str:
        return self.settings.get("playit_path", "")

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
        if name in self.servers: return False
        s_dir = self.servers_dir / name
        if s_dir.exists(): return False
        try:
            s_dir.mkdir(parents=True, exist_ok=True)
            jar_name = Path(jar_source).name
            shutil.copy2(jar_source, s_dir / jar_name)
            with open(s_dir / "start.bat", "w") as f:
                f.write(f"java -Xmx{ram_mb}M -Xms{ram_mb}M -jar {jar_name} nogui\npause")
            with open(s_dir / "eula.txt", "w") as f: f.write("eula=true\n")
            new_server = ServerData(name, jar_name, str(s_dir / jar_name), ram_mb, str(s_dir))
            self.servers[name] = new_server
            self.save_servers()
            return True
        except: return False

    def delete_server(self, name: str) -> bool:
        if name not in self.servers: return False
        if self.active_instance and self.active_instance.data.name == name and self.active_instance.state != ServerState.OFFLINE:
            return False
        server = self.servers.pop(name)
        try:
            if os.path.exists(server.directory): shutil.rmtree(server.directory)
        except: pass
        self.save_servers()
        return True

    def rename_server(self, old_name: str, new_name: str) -> bool:
        if new_name in self.servers or old_name not in self.servers: return False
        server = self.servers.pop(old_name)
        server.name = new_name
        self.servers[new_name] = server
        self.save_servers()
        return True

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
        server = self.servers.get(server_name)
        if not server: return
        path = Path(server.directory) / "server.properties"
        if not path.exists(): return
        lines = []
        with open(path, "r") as f: lines = f.readlines()
        with open(path, "w") as f:
            for line in lines:
                if "=" in line and not line.strip().startswith("#"):
                    k, _ = line.strip().split("=", 1)
                    if k in new_props:
                        f.write(f"{k}={new_props[k]}\n")
                    else:
                        f.write(line)
                else:
                    f.write(line)

    @staticmethod
    def get_dir_size_gb(path: str) -> float:
        return get_directory_size_gb(path)

    @staticmethod
    def get_local_ip() -> str:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except: return "127.0.0.1"

    @staticmethod
    def get_public_ip() -> str:
        try:
            return urllib.request.urlopen('https://api.ipify.org').read().decode('utf8')
        except: return "Unavailable"