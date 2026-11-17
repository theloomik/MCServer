"""Read which Minecraft release (and Java requirement) a server JAR is built for."""

from __future__ import annotations

import json
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path

from mcserver.domain.java_requirements import MinecraftVersion, parse_minecraft_version

_NAME_VERSION = re.compile(r"(?<![\d.])(\d+\.\d+(?:\.\d+)?)(?![\d.])")
_MAX_VERSION_JSON_BYTES = 64 * 1024


@dataclass(frozen=True, slots=True)
class JarVersion:
    """What could be learned about a server JAR; any field may be unknown."""

    version_text: str | None
    version: MinecraftVersion | None
    declared_java_major: int | None
    """``java_version`` from the JAR's own ``version.json`` (Mojang server JARs), if present."""


def read_jar_version(jar_path: Path) -> JarVersion:
    """Read ``version.json`` inside the JAR, falling back to a version in the file name (``paper-1.21.1-1.jar``)."""
    text: str | None = None
    declared: int | None = None
    try:
        with zipfile.ZipFile(jar_path) as archive:
            info = archive.getinfo("version.json")
            if info.file_size <= _MAX_VERSION_JSON_BYTES:
                data = json.loads(archive.read(info).decode("utf-8", errors="replace"))
                if isinstance(data, dict):
                    candidate = data.get("id") or data.get("name")
                    if isinstance(candidate, str):
                        text = candidate
                    java = data.get("java_version")
                    if isinstance(java, int) and not isinstance(java, bool):
                        declared = java
    except (OSError, KeyError, ValueError, zipfile.BadZipFile):
        pass
    if text is None:
        match = _NAME_VERSION.search(jar_path.name)
        text = match.group(1) if match else None
    version = parse_minecraft_version(text) if text else None
    return JarVersion(text, version, declared)
