"""Adapters for external systems that implement application-layer interfaces."""

from mcserver.infrastructure.java_runtime import JavaRuntime, JavaRuntimeResolver, JavaRuntimeSource
from mcserver.infrastructure.legacy_import import LegacyImportReport, LegacyServerConfigurationImporter
from mcserver.infrastructure.process_runner import MinecraftProcessConfig, SubprocessServerRunner
from mcserver.infrastructure.server_configuration import (
    ConfiguredServerRunnerFactory,
    LegacyServerConfigurationRepository,
)
from mcserver.infrastructure.server_configuration_store import (
    JsonServerConfigurationRepository,
    StoredServerLaunchSettings,
)

__all__ = [
    "ConfiguredServerRunnerFactory",
    "JavaRuntime",
    "JavaRuntimeResolver",
    "JavaRuntimeSource",
    "JsonServerConfigurationRepository",
    "LegacyImportReport",
    "LegacyServerConfigurationImporter",
    "LegacyServerConfigurationRepository",
    "MinecraftProcessConfig",
    "StoredServerLaunchSettings",
    "SubprocessServerRunner",
]
