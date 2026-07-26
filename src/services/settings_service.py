from __future__ import annotations

import flet as ft


THEMES: dict[str, ft.ThemeMode] = {
    "SYSTEM": ft.ThemeMode.SYSTEM,
    "DARK": ft.ThemeMode.DARK,
    "LIGHT": ft.ThemeMode.LIGHT,
}

LANGUAGES = ["English", "Русский", "Українська"]


class SettingsService:
    def __init__(self, page: ft.Page):
        self._page = page

    async def load_settings(self) -> dict:
        sp = self._page.shared_preferences
        theme = await sp.get("types_editor.theme")
        lang = await sp.get("types_editor.language")
        updates = await sp.get("types_editor.check_updates")
        return {"theme": theme, "language": lang, "check_updates": updates}

    async def save_setting(self, key: str, value):
        await self._page.shared_preferences.set(f"types_editor.{key}", value)
