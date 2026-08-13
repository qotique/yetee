from __future__ import annotations

import pytest

from mod_handlers import (
    AS_Mods,
    CommunityOnlineTools,
    NotYetAvailableMod,
    PermissionsFramework,
    SpawnerBubaku,
    TraderX,
    get_mod_handler,
    is_not_yet_available,
)
from custom_entities import RENDERER_TXT

EXPECTED_MODS = {
    "TraderX",
    "CommunityOnlineTools",
    "PermissionsFramework",
    "SpawnerBubaku",
    "AS_Mods",
}


@pytest.mark.parametrize("name", sorted(EXPECTED_MODS))
def test_known_mods_are_not_yet_available(name):
    assert is_not_yet_available(name) is True


def test_unknown_entity_not_marked():
    assert is_not_yet_available("SomeOtherMod") is False


def test_get_mod_handler_returns_instances():
    for name in EXPECTED_MODS:
        handler = get_mod_handler(name)
        assert handler is not None
        assert handler.name == name
        assert isinstance(handler, NotYetAvailableMod)


def test_subclass_names_match_directories():
    assert TraderX().name == "TraderX"
    assert CommunityOnlineTools().name == "CommunityOnlineTools"
    assert PermissionsFramework().name == "PermissionsFramework"
    assert SpawnerBubaku().name == "SpawnerBubaku"
    assert AS_Mods().name == "AS_Mods"


def test_default_message():
    handler = TraderX()
    assert "not available yet" in handler.message


def test_get_renderer_returns_txt():
    handler = TraderX()
    assert handler.get_renderer("whatever.xml") == RENDERER_TXT