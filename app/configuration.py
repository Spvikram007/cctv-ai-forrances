"""
Application Configuration Helper.
Provides access to unified platform settings and runtime configuration updates.
"""

from typing import Optional
from core.config.settings import PlatformSettings, settings

_runtime_settings: Optional[PlatformSettings] = None


def get_settings() -> PlatformSettings:
    """Returns the active platform settings singleton."""
    global _runtime_settings
    if _runtime_settings is None:
        _runtime_settings = settings
        _runtime_settings.ensure_directories()
    return _runtime_settings


def reload_settings() -> PlatformSettings:
    """Reloads settings from environment variables and .env file."""
    global _runtime_settings
    _runtime_settings = PlatformSettings()
    _runtime_settings.ensure_directories()
    return _runtime_settings
