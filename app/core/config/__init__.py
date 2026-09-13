"""类型化配置的公共入口"""

from app.core.config.app import Environment
from app.core.config.settings import Settings, get_settings

__all__ = ["Environment", "Settings", "get_settings"]
