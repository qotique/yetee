from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Protocol

logger = logging.getLogger(__name__)

THEME_KEYS: tuple[str, ...] = ("SYSTEM", "DARK", "LIGHT")
LANGUAGE_NAMES: tuple[str, ...] = ("English", "Русский", "Українська")

FUN_FLAG_KEYS: tuple[str, ...] = (
    "fun_save_messages",
    "show_meme_on_save",
    "cat_mode",
    "terminal_mode",
    "funny_enabled",
)


class SettingsStore(Protocol):
    async def load_settings(self) -> dict[str, object]: ...
    async def save_setting(self, key: str, value: object) -> None: ...


class EntertainmentFlags(Protocol):
    fun_save_messages: bool
    show_meme_on_save: bool
    cat_mode: bool
    terminal_mode: bool
    funny_enabled: bool
    achievements_str: str


class SettingsManager:
    def __init__(
        self,
        settings_service: SettingsStore,
        entertainment_service: EntertainmentFlags,
    ) -> None:
        self._settings = settings_service
        self._entertainment = entertainment_service
        self.selected_theme: str = "SYSTEM"
        self.selected_language: str = "English"
        self.check_updates: bool = True
        self.show_unhandled_mod_editors: bool = False

    def apply_startup(self, settings: Mapping[str, object]) -> None:
        theme = settings.get("theme")
        if isinstance(theme, str) and theme in THEME_KEYS:
            self.selected_theme = theme
        lang = settings.get("language")
        if isinstance(lang, str) and lang in LANGUAGE_NAMES:
            self.selected_language = lang
        updates = settings.get("check_updates")
        if isinstance(updates, bool):
            self.check_updates = updates
        for key in FUN_FLAG_KEYS:
            value = settings.get(key)
            if isinstance(value, bool):
                setattr(self._entertainment, key, value)
        unhandled = settings.get("show_unhandled_mod_editors")
        if isinstance(unhandled, bool):
            self.show_unhandled_mod_editors = unhandled
        achievements_raw = settings.get("achievements")
        if isinstance(achievements_raw, str):
            self._entertainment.achievements_str = achievements_raw

    async def save(self, key: str, value: object) -> None:
        try:
            await self._settings.save_setting(key, value)
        except Exception as ex:
            logger.error("Failed to save %s setting: %s", key, ex)

    async def set_theme(self, value: object) -> bool:
        if not isinstance(value, str) or value not in THEME_KEYS:
            return False
        self.selected_theme = value
        await self.save("theme", value)
        return True

    async def set_language(self, value: object) -> bool:
        if not isinstance(value, str) or value not in LANGUAGE_NAMES:
            return False
        self.selected_language = value
        await self.save("language", value)
        return True

    async def set_check_updates(self, value: bool) -> None:
        self.check_updates = value
        await self.save("check_updates", value)

    async def set_unhandled_editors(self, value: bool) -> None:
        self.show_unhandled_mod_editors = value
        await self.save("show_unhandled_mod_editors", value)

    async def set_fun_flag(self, key: str, value: bool) -> None:
        if key not in FUN_FLAG_KEYS:
            logger.warning("Unknown fun flag: %s", key)
            return
        setattr(self._entertainment, key, value)
        await self.save(key, value)
