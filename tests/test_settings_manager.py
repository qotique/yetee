from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from controllers.settings_manager import (
    FUN_FLAG_KEYS,
    LANGUAGE_NAMES,
    THEME_KEYS,
    SettingsManager,
)
from services.entertainment_service import EntertainmentService
from services.settings_service import LANGUAGES, THEMES


def test_theme_keys_match_settings_service():
    assert set(THEME_KEYS) == set(THEMES.keys())


def test_language_names_match_settings_service():
    assert list(LANGUAGE_NAMES) == list(LANGUAGES)


@pytest.fixture
def manager():
    store = MagicMock()
    ent = EntertainmentService()
    return SettingsManager(store, ent), store, ent


async def test_defaults(manager):
    mgr, _, _ = manager
    assert mgr.selected_theme == "SYSTEM"
    assert mgr.selected_language == "English"
    assert mgr.check_updates is True
    assert mgr.show_unhandled_mod_editors is False


async def test_apply_startup_applies_known_keys(manager):
    mgr, _, ent = manager
    mgr.apply_startup(
        {
            "theme": "DARK",
            "language": "Русский",
            "check_updates": False,
            "cat_mode": True,
            "funny_enabled": True,
            "show_unhandled_mod_editors": True,
            "achievements": "10,50",
        }
    )
    assert mgr.selected_theme == "DARK"
    assert mgr.selected_language == "Русский"
    assert mgr.check_updates is False
    assert ent.cat_mode is True
    assert ent.funny_enabled is True
    assert mgr.show_unhandled_mod_editors is True
    assert ent.achievements_str == "10,50"


async def test_apply_startup_ignores_invalid_values(manager):
    mgr, _, _ = manager
    mgr.apply_startup({"theme": "NEON", "check_updates": "yes", 42: 1})
    assert mgr.selected_theme == "SYSTEM"
    assert mgr.check_updates is True


async def test_set_theme_validates_and_persists(manager):
    mgr, store, _ = manager
    assert await mgr.set_theme("DARK") is True
    assert mgr.selected_theme == "DARK"
    store.save_setting.assert_called_once_with("theme", "DARK")


async def test_set_theme_rejects_invalid(manager):
    mgr, store, _ = manager
    assert await mgr.set_theme("NEON") is False
    store.save_setting.assert_not_called()


async def test_set_language_validates(manager):
    mgr, store, _ = manager
    assert await mgr.set_language("Українська") is True
    assert await mgr.set_language("Deutsch") is False
    store.save_setting.assert_called_once_with("language", "Українська")


async def test_set_check_updates_persists(manager):
    mgr, store, _ = manager
    await mgr.set_check_updates(False)
    assert mgr.check_updates is False
    store.save_setting.assert_called_once_with("check_updates", False)


async def test_set_unhandled_editors_persists(manager):
    mgr, store, _ = manager
    await mgr.set_unhandled_editors(True)
    assert mgr.show_unhandled_mod_editors is True
    store.save_setting.assert_called_once_with("show_unhandled_mod_editors", True)


async def test_set_fun_flag_updates_service(manager):
    mgr, store, ent = manager
    await mgr.set_fun_flag("terminal_mode", True)
    assert ent.terminal_mode is True
    store.save_setting.assert_called_once_with("terminal_mode", True)


async def test_set_fun_flag_rejects_unknown_key(manager):
    mgr, store, ent = manager
    await mgr.set_fun_flag("nope", True)
    store.save_setting.assert_not_called()


def test_fun_flag_keys_are_entertainment_attributes():
    ent = EntertainmentService()
    for key in FUN_FLAG_KEYS:
        assert hasattr(ent, key)


async def test_save_swallows_store_errors(manager):
    mgr, store, _ = manager

    async def boom(key: str, value: object) -> None:
        raise RuntimeError("closed")

    store.save_setting.side_effect = boom
    await mgr.set_check_updates(False)
    assert mgr.check_updates is False
