"""Adapters for external systems that implement application-layer interfaces."""

from mcserver.infrastructure.java_runtime import JavaRuntime, JavaRuntimeResolver, JavaRuntimeSource
from mcserver.infrastructure.legacy_import import LegacyFileServerConfigurationSource
from mcserver.infrastructure.process_runner import MinecraftProcessConfig, SubprocessServerRunner
from mcserver.infrastructure.server_configuration import (
    ConfiguredServerRunnerFactory,
    LegacyServerConfigurationRepository,
)
from mcserver.infrastructure.server_configuration_store import (
    JsonServerConfigurationRepository,
    StoredServerLaunchSettings,
)
from mcserver.infrastructure.server_files import LocalServerFilesystem

__all__ = [
    "ConfiguredServerRunnerFactory",
    "JavaRuntime",
    "JavaRuntimeResolver",
    "JavaRuntimeSource",
    "JsonServerConfigurationRepository",
    "LegacyFileServerConfigurationSource",
    "LegacyServerConfigurationRepository",
    "LocalServerFilesystem",
    "MinecraftProcessConfig",
    "StoredServerLaunchSettings",
    "SubprocessServerRunner",
]
