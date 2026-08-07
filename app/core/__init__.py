"""Cross-cutting concerns: configuration, security and error handling."""

from app.core.config import Settings, get_settings

__all__ = ["Settings", "get_settings"]
