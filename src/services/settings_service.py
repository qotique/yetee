from __future__ import annotations

import logging

import flet as ft

logger = logging.getLogger(__name__)


THEMES: dict[str, ft.ThemeMode] = {
    "SYSTEM": ft.ThemeMode.SYSTEM,
    "DARK": ft.ThemeMode.DARK,
    "LIGHT": ft.ThemeMode.LIGHT,
}

LANGUAGES = ["English", "Русский", "Українська"]


class SettingsService:
    def __init__(self, page: ft.Page) -> None:
        self._page = page

    async def load_settings(self) -> dict[str, object]:
        logger.debug("Loading settings")
        sp = self._page.shared_preferences
        keys = [
            "theme", "language", "check_updates",
            "fun_sounds", "fun_save_messages", "show_meme_on_save",
            "cat_mode", "terminal_mode", "funny_enabled",
            "achievements",
        ]
        try:
            result: dict[str, object] = {}
            for key in keys:
                val = await sp.get(f"types_editor.{key}")
                if val is not None:
                    result[key] = val
            logger.debug("Settings loaded: %s", result)
            return result
        except Exception as ex:
            logger.error("Failed to load settings: %s", ex)
            return {}

    async def save_setting(self, key: str, value: object) -> None:
        logger.debug("Saving setting %s=%s", key, value)
        try:
            await self._page.shared_preferences.set(f"types_editor.{key}", value)
        except Exception as ex:
            logger.error("Failed to save setting %s: %s", key, ex)
