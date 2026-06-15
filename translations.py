import threading


STRINGS = {
    "APP_TITLE": {"uk": "MCServer", "en": "MCServer"},
    "APP_WELCOME_TITLE": {"uk": "Вітаємо в MCServer", "en": "Welcome to MCServer"},
    "APP_WELCOME_SUB": {
        "uk": "Оберіть сервер у меню зліва або створіть новий",
        "en": "Select a server in the left menu or create a new one",
    },
    "SIDEBAR_ALL_SERVERS": {"uk": "ВСІ СЕРВЕРИ", "en": "ALL SERVERS"},
    "SIDEBAR_SEARCH": {"uk": "🔍 Пошук сервера...", "en": "🔍 Search server..."},
    "SIDEBAR_NEW_SERVER": {"uk": "+ Створити сервер", "en": "+ Create Server"},
    "SIDEBAR_LOGO": {"uk": "🟩 MCServer", "en": "🟩 MCServer"},

    "STATUS_ONLINE": {"uk": "● ONLINE", "en": "● ONLINE"},
    "STATUS_STARTING": {"uk": "↻ STARTING", "en": "↻ STARTING"},
    "STATUS_STOPPING": {"uk": "⏹ STOPPING", "en": "⏹ STOPPING"},
    "STATUS_OFFLINE": {"uk": "○ OFFLINE", "en": "○ OFFLINE"},
    "METRIC_OFFLINE": {"uk": "OFFLINE", "en": "OFFLINE"},

    "DASH_TITLE_DEFAULT": {"uk": "Назва Сервера", "en": "Server Name"},
    "DASH_DESC_CORE_VER": {"uk": "Ядро: {core} | Версія: {ver}", "en": "Core: {core} | Version: {ver}"},
    "DASH_DESC_UNKNOWN": {"uk": "Ядро: Unknown | Версія: Unknown", "en": "Core: Unknown | Version: Unknown"},
    "DASH_UPTIME": {"uk": "⏱ Uptime: {uptime}", "en": "⏱ Uptime: {uptime}"},
    "DASH_UPTIME_ZERO": {"uk": "⏱ Uptime: 0 год 0 хв 0 с", "en": "⏱ Uptime: 0 h 0 m 0 s"},
    "DASH_PLAYERS": {"uk": "👥 Players: {cur} / {max_p}", "en": "👥 Players: {cur} / {max_p}"},
    "DASH_PLAYERS_DEFAULT": {"uk": "👥 Players: 0 / 20", "en": "👥 Players: 0 / 20"},
    "DASH_SECTION_CONTROL": {"uk": "КЕРУВАННЯ", "en": "CONTROL"},
    "DASH_SECTION_MONITOR": {"uk": "МОНІТОРИНГ", "en": "MONITORING"},
    "DASH_TERMINAL_TITLE": {"uk": "Terminal >_", "en": "Terminal >_"},
    "DASH_BTN_START": {"uk": "▶ Запуск", "en": "▶ Start"},
    "DASH_BTN_STOP": {"uk": "⏹ Стоп", "en": "⏹ Stop"},
    "DASH_BTN_RESTART": {"uk": "🔄 Рестарт", "en": "🔄 Restart"},
    "DASH_BTN_PROPS": {"uk": "📝 Конфігурація", "en": "📝 Configuration"},
    "DASH_BTN_SETTINGS": {"uk": "🛠 Налаштування", "en": "🛠 Settings"},
    "DASH_BTN_FOLDER": {"uk": "📂 Відкрити папку", "en": "📂 Open Folder"},
    "DASH_BTN_SAVE_LOG": {"uk": "Зберегти", "en": "Save"},
    "DASH_BTN_CLEAR_LOG": {"uk": "Очистити", "en": "Clear"},
    "DASH_BTN_SEND": {"uk": "Надіслати", "en": "Send"},
    "DASH_TIP_SAVE_LOG": {"uk": "Зберегти лог", "en": "Save log"},
    "DASH_TIP_CLEAR_LOG": {"uk": "Очистити консоль", "en": "Clear console"},
    "DASH_PH_CONSOLE": {"uk": "Логи сервера з'являться тут...", "en": "Server logs will appear here..."},
    "DASH_PH_CMD": {"uk": "Введіть команду...", "en": "Enter command..."},
    "DASH_BTN_BUSY": {"uk": "Зайнято", "en": "Busy"},
    "DASH_BTN_STARTING": {"uk": "Запуск...", "en": "Starting..."},
    "DASH_BTN_RUNNING": {"uk": "Працює", "en": "Running"},
    "DASH_BTN_STOPPING": {"uk": "Зупинка...", "en": "Stopping..."},
    "DASH_BTN_KILL": {"uk": "💀 Вбити!", "en": "💀 Kill!"},
    "DASH_BTN_KILLED": {"uk": "Вбито", "en": "Killed"},
    "DASH_MSG_LOG_EMPTY": {"uk": "Лог порожній", "en": "Log is empty"},
    "DASH_MSG_LOG_SAVED": {"uk": "Лог збережено!", "en": "Log saved!"},
    "DASH_MSG_LOG_SAVE_ERR": {"uk": "Помилка збереження", "en": "Save error"},
    "DASH_MSG_FOLDER_ERR": {"uk": "Помилка відкриття папки", "en": "Failed to open folder"},
    "DASH_MSG_PROCESS_EXIT": {"uk": "Процес завершився (Код {code})", "en": "Process exited (Code {code})"},

    "PROPS_TITLE": {"uk": "Конфігурація (server.properties)", "en": "Configuration (server.properties)"},
    "PROPS_SEARCH": {"uk": "🔍 Пошук налаштувань...", "en": "🔍 Search settings..."},
    "PROPS_LOADING": {"uk": "Завантаження конфігурації...", "en": "Loading configuration..."},
    "PROPS_BTN_SAVE": {"uk": "Зберегти зміни", "en": "Save changes"},
    "PROPS_MSG_SAVED": {"uk": "Конфігурацію збережено!", "en": "Configuration saved!"},
    "PROPS_BOOL_ENABLED": {"uk": "Увімкнено", "en": "Enabled"},

    "SETTINGS_TITLE": {"uk": "Налаштування", "en": "Settings"},
    "SETTINGS_BACK": {"uk": "Назад", "en": "Back"},
    "SETTINGS_SECTION_GENERAL": {"uk": "Загальні", "en": "General"},
    "SETTINGS_SECTION_NETWORK": {"uk": "Мережа", "en": "Network"},
    "SETTINGS_SECTION_DANGER": {"uk": "Небезпечна зона", "en": "Danger zone"},
    "SETTINGS_RAM_ALLOC": {"uk": "Виділена пам'ять (RAM)", "en": "Allocated memory (RAM)"},
    "SETTINGS_BTN_SAVE_RAM": {"uk": "Зберегти RAM", "en": "Save RAM"},
    "SETTINGS_NETWORK_DESC": {"uk": "Керування IP та віддаленим доступом", "en": "Manage IP and remote access"},
    "SETTINGS_BTN_OPEN_NETWORK": {"uk": "🌐 Відкрити меню мережі", "en": "🌐 Open network menu"},
    "SETTINGS_BTN_DELETE": {"uk": "💀 Видалити сервер", "en": "💀 Delete server"},
    "SETTINGS_MSG_RAM_UPDATED": {"uk": "RAM оновлено!", "en": "RAM updated!"},
    "SETTINGS_MSG_SERVER_DELETED": {"uk": "Сервер видалено!", "en": "Server deleted!"},
    "SETTINGS_DELETE_CONFIRM_TITLE": {"uk": "Підтвердження видалення", "en": "Confirm deletion"},
    "SETTINGS_DELETE_CONFIRM_TEXT": {
        "uk": "Назавжди видалити сервер '{name}' та всі його світи й файли?",
        "en": "Permanently delete server '{name}' and all of its worlds and files?",
    },
    "SETTINGS_MSG_STOP_BEFORE_DELETE": {
        "uk": "Зупиніть сервер перед видаленням!",
        "en": "Stop the server before deleting!",
    },
    "SETTINGS_MSG_DELETE_FAILED": {
        "uk": "Не вдалося безпечно видалити сервер.",
        "en": "Could not safely delete the server.",
    },
    "SETTINGS_SECTION_LANGUAGE": {"uk": "Мова / Language", "en": "Language / Мова"},
    "SETTINGS_LANGUAGE_LABEL": {"uk": "Мова інтерфейсу", "en": "Interface language"},
    "SETTINGS_LANG_UK": {"uk": "Українська", "en": "Ukrainian"},
    "SETTINGS_LANG_EN": {"uk": "English", "en": "English"},
    "SETTINGS_LANG_RESTART": {
        "uk": "Мову збережено. Перезапустіть програму для застосування змін.",
        "en": "Language saved. Restart the app to apply changes.",
    },

    "CREATE_TITLE": {"uk": "Створення Сервера", "en": "Create Server"},
    "CREATE_PH_NAME": {"uk": "Назва сервера (напр. Survival)", "en": "Server name (e.g. Survival)"},
    "CREATE_PH_JAR": {"uk": "Шлях до ядра (.jar)", "en": "Path to core (.jar)"},
    "CREATE_RAM_LABEL": {"uk": "RAM: {value} GB", "en": "RAM: {value} GB"},
    "RAM_VALUE_GB": {"uk": "{value} GB", "en": "{value} GB"},
    "RAM_MIN_LABEL": {"uk": "1 GB", "en": "1 GB"},
    "RAM_MAX_LABEL": {"uk": "16 GB", "en": "16 GB"},
    "CREATE_BTN_CREATE": {"uk": "Створити сервер", "en": "Create server"},
    "CREATE_BTN_CANCEL": {"uk": "Скасувати", "en": "Cancel"},
    "CREATE_DLG_PICK_JAR": {"uk": "Виберіть ядро", "en": "Select core"},
    "CREATE_MSG_FILL_FIELDS": {"uk": "Заповніть всі поля!", "en": "Fill all fields!"},
    "CREATE_MSG_CREATED": {"uk": "Сервер '{name}' створено!", "en": "Server '{name}' created!"},
    "CREATE_MSG_CREATE_ERR": {"uk": "Помилка створення", "en": "Creation failed"},

    "NETWORK_TITLE": {"uk": "Мережа та Доступ", "en": "Network & Access"},
    "NETWORK_IP_CARD_TITLE": {"uk": "IP Адреси (Виділіть, щоб скопіювати)", "en": "IP Addresses (Select to copy)"},
    "NETWORK_LOCAL_LABEL": {"uk": "🏠 Локальна:  {ip}", "en": "🏠 Local:  {ip}"},
    "NETWORK_LOCAL_DOTS": {"uk": "Локальна: ...", "en": "Local: ..."},
    "NETWORK_PUBLIC_OFF": {"uk": "Публічна (Playit): Тунель вимкнено", "en": "Public (Playit): Tunnel is off"},
    "NETWORK_PLAYIT_TITLE": {"uk": "Playit.gg (Віддалений доступ)", "en": "Playit.gg (Remote access)"},
    "NETWORK_PLAYIT_DESC": {"uk": "Грайте з друзями без відкриття портів.", "en": "Play with friends without opening ports."},
    "NETWORK_BTN_DOWNLOAD": {"uk": "Завантажити", "en": "Download"},
    "NETWORK_PH_PLAYIT": {"uk": "Шлях до playit.exe", "en": "Path to playit.exe"},
    "NETWORK_BTN_RUN": {"uk": "🚀 Запустити Тунель", "en": "🚀 Start Tunnel"},
    "NETWORK_BTN_STOP": {"uk": "⏹ Зупинити Тунель", "en": "⏹ Stop Tunnel"},
    "NETWORK_PH_LOGS": {"uk": "Логи Playit...", "en": "Playit logs..."},
    "NETWORK_DLG_FIND_PLAYIT": {"uk": "Знайти playit.exe", "en": "Find playit.exe"},
    "NETWORK_MSG_BAD_PLAYIT_PATH": {"uk": "Вкажіть правильний шлях до playit.exe!", "en": "Specify a valid path to playit.exe!"},
    "NETWORK_MSG_PLAYIT_START_FAIL": {"uk": "Не вдалося запустити playit.exe", "en": "Failed to start playit.exe"},
    "NETWORK_PUBLIC_LABEL": {"uk": "🌍 Публічна: {ip}", "en": "🌍 Public: {ip}"},
    "NETWORK_MSG_IP_COPIED": {"uk": "IP скопійовано!", "en": "IP copied!"},

    "HOME_NAV_BACK": {"uk": "Назад", "en": "Back"},
    "FILTER_INFO": {"uk": "INFO", "en": "INFO"},
    "FILTER_WARN": {"uk": "WARN", "en": "WARN"},
    "FILTER_ERR": {"uk": "ERR", "en": "ERR"},

    "CORE_ERR_JAVA_NOT_FOUND": {"uk": "ERROR: Java не знайдено!\n", "en": "ERROR: Java not found!\n"},
    "CORE_LOG_SERVER_START": {"uk": "--- Запуск сервера: {name} ---\n", "en": "--- Starting server: {name} ---\n"},
    "CORE_ERR_START_FAIL": {"uk": "Не вдалося запустити: {error}\n", "en": "Failed to start: {error}\n"},
    "CORE_ERR_PORT_BUSY": {
        "uk": "ERROR: Порт {port} вже зайнятий. Змініть server-port або зупиніть інший сервер.\n",
        "en": "ERROR: Port {port} is already in use. Change server-port or stop the other server.\n",
    },
    "CORE_LOG_STOP_SENT": {"uk": "--- Команду stop надіслано ---\n", "en": "--- Stop command sent ---\n"},
    "CORE_ERR_KILL": {"uk": "Помилка kill: {error}\n", "en": "Kill error: {error}\n"},
    "CORE_UPTIME_FMT": {"uk": "{h} год {m} хв {s} с", "en": "{h} h {m} m {s} s"},
    "CORE_UPTIME_ZERO": {"uk": "0 год 0 хв 0 с", "en": "0 h 0 m 0 s"},
    "CORE_PLAYIT_EXITED": {"uk": "Процес Playit завершився неочікувано.", "en": "Playit process exited unexpectedly."},
    "CORE_PLAYIT_START_ERR": {"uk": "Помилка запуску playit: {error}", "en": "Error starting playit: {error}"},
    "CORE_UNAVAILABLE": {"uk": "Недоступно", "en": "Unavailable"},

    "CORE_TYPE_PAPER": {"uk": "Paper", "en": "Paper"},
    "CORE_TYPE_PURPUR": {"uk": "Purpur", "en": "Purpur"},
    "CORE_TYPE_SPIGOT": {"uk": "Spigot", "en": "Spigot"},
    "CORE_TYPE_BUKKIT": {"uk": "Bukkit", "en": "Bukkit"},
    "CORE_TYPE_FABRIC": {"uk": "Fabric", "en": "Fabric"},
    "CORE_TYPE_FORGE": {"uk": "Forge", "en": "Forge"},
    "CORE_TYPE_VANILLA": {"uk": "Vanilla", "en": "Vanilla"},
    "CORE_TYPE_UNKNOWN": {"uk": "Unknown", "en": "Unknown"},

    "PROP_DESC_GAMEMODE": {
        "uk": "Режим гри за замовчуванням (survival, creative).",
        "en": "Default game mode (survival, creative).",
    },
    "PROP_DESC_DIFFICULTY": {"uk": "Складність світу.", "en": "World difficulty."},
    "PROP_DESC_MOTD": {"uk": "Опис сервера у списку (Message of the Day).", "en": "Server list description (Message of the Day)."},
    "PROP_DESC_MAX_PLAYERS": {"uk": "Максимальна кількість гравців.", "en": "Maximum concurrent players."},
    "PROP_DESC_SERVER_PORT": {"uk": "Порт сервера (стандарт 25565).", "en": "Server port (default 25565)."},
    "PROP_DESC_PVP": {"uk": "Битви між гравцями.", "en": "Player versus player combat."},
    "PROP_DESC_ONLINE_MODE": {"uk": "true = ліцензійні акаунти, false = offline-mode.", "en": "true = premium accounts, false = offline-mode."},
    "PROP_DESC_ALLOW_FLIGHT": {"uk": "Дозволити політ (потрібно для деяких модів).", "en": "Allow flight (required by some mods)."},
    "PROP_DESC_WHITE_LIST": {"uk": "Доступ лише для гравців зі списку.", "en": "Allow only whitelisted players."},
    "PROP_DESC_VIEW_DISTANCE": {"uk": "Дальність промальовки чанків. Впливає на RAM.", "en": "Chunk render distance. Affects RAM usage."},
    "PROP_DESC_SIM_DISTANCE": {"uk": "Дальність симуляції механізмів і мобів.", "en": "Simulation distance for entities and mechanics."},
    "PROP_DESC_LEVEL_SEED": {"uk": "Seed генерації світу.", "en": "World generation seed."},
    "PROP_DESC_HARDCORE": {"uk": "Hardcore-режим (бан після смерті).", "en": "Hardcore mode (ban on death)."},
    "PROP_DESC_SPAWN_PROTECTION": {"uk": "Радіус захисту спавну (у блоках).", "en": "Spawn protection radius (blocks)."},
    "PROP_DESC_COMMAND_BLOCK": {"uk": "Увімкнути командні блоки.", "en": "Enable command blocks."},
    "PROP_DESC_SPAWN_MONSTERS": {"uk": "Спавн ворожих мобів.", "en": "Allow hostile mob spawning."},
    "PROP_DESC_SPAWN_ANIMALS": {"uk": "Спавн тварин.", "en": "Allow animal spawning."},
    "PROP_DESC_SPAWN_NPCS": {"uk": "Спавн NPC (жителі тощо).", "en": "Allow NPC spawning."},
    "PROP_DESC_ALLOW_NETHER": {"uk": "Дозволити вимір Nether.", "en": "Allow Nether dimension."},
    "PROP_DESC_LEVEL_TYPE": {"uk": "Тип світу (minecraft:normal, flat, large_biomes).", "en": "World type (minecraft:normal, flat, large_biomes)."},
    "PROP_DESC_GEN_STRUCT": {"uk": "Генерувати структури (села, данжі тощо).", "en": "Generate structures (villages, dungeons, etc.)."},
    "PROP_DESC_MAX_BUILD_HEIGHT": {"uk": "Максимальна висота будівництва.", "en": "Maximum build height."},
    "PROP_DESC_RATE_LIMIT": {"uk": "Ліміт мережевих пакетів (0 = вимкнено).", "en": "Network packet rate limit (0 = disabled)."},
    "PROP_DESC_RESOURCE_PACK": {"uk": "URL ресурспаку.", "en": "Resource pack URL."},
    "PROP_DESC_ENFORCE_WHITELIST": {"uk": "Примусово застосовувати whitelist.", "en": "Enforce whitelist on join/reload."},
    "PROP_DESC_ENTITY_BROADCAST": {"uk": "Дальність трансляції сутностей (%).", "en": "Entity broadcast range percentage (%)."},
    "PROP_DESC_ENABLE_QUERY": {"uk": "Увімкнути GameSpy4 Query протокол.", "en": "Enable GameSpy4 Query protocol."},
    "PROP_DESC_ENABLE_RCON": {"uk": "Увімкнути віддалену консоль RCON.", "en": "Enable remote console (RCON)."},
    "PROP_DESC_SYNC_CHUNK_WRITES": {"uk": "Синхронний запис чанків (стабільність I/O).", "en": "Synchronous chunk writes (I/O stability)."},
    "PROP_DESC_NET_COMPRESS": {"uk": "Поріг стиснення пакетів (байти).", "en": "Network compression threshold (bytes)."},
    "PROP_DESC_PREVENT_PROXY": {"uk": "Блокувати проксі/VPN підключення.", "en": "Block proxy/VPN connections."},

    "EULA_TITLE": {"uk": "Ліцензійна угода Minecraft", "en": "Minecraft License Agreement"},
    "EULA_TEXT": {
        "uk": "Для запуску сервера необхідно прийняти ліцензійну угоду Minecraft (EULA).\n\nПовний текст: https://aka.ms/MinecraftEULA\n\nВи погоджуєтесь з умовами?",
        "en": "To start the server you must accept the Minecraft End User License Agreement (EULA).\n\nFull text: https://aka.ms/MinecraftEULA\n\nDo you agree to the terms?",
    },

    "NETWORK_DLG_SAVE_PLAYIT": {"uk": "Зберегти playit.exe", "en": "Save playit.exe"},
    "NETWORK_DL_CHECKING": {"uk": "Перевірка останнього релізу на GitHub...", "en": "Checking latest release on GitHub..."},
    "NETWORK_DL_PROGRESS": {"uk": "Завантаження {version}...", "en": "Downloading {version}..."},
    "NETWORK_DL_OK": {
        "uk": "✓ Завантажено ({version})\nSHA-256: {sha}\n(збережіть хеш для перевірки цілісності)",
        "en": "✓ Downloaded ({version})\nSHA-256: {sha}\n(save this hash to verify file integrity)",
    },
    "NETWORK_DL_ERR": {"uk": "Помилка завантаження: {error}", "en": "Download error: {error}"},
}


class Translator:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._lang = "uk"
        return cls._instance

    def set_language(self, lang_code: str):
        self._lang = "en" if lang_code == "en" else "uk"

    def get_language(self) -> str:
        return self._lang

    def get(self, key: str, **kwargs) -> str:
        entry = STRINGS.get(key)
        if not entry:
            return key
        text = entry.get(self._lang) or entry.get("uk") or key
        if kwargs:
            try:
                return text.format(**kwargs)
            except Exception:
                return text
        return text


def _t(key: str, **kwargs) -> str:
    return Translator().get(key, **kwargs)
