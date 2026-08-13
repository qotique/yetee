from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from models.project import Project
from services.profile_service import ProfileService
from unavailable_display import UnavailableDisplay
from ui.economy_editor import EconomyEditor


@pytest.fixture
def mock_page():
    page = MagicMock()
    page.theme = None
    page.dark_theme = None
    page.on_keyboard_event = None
    mock_task = MagicMock()
    mock_task.done.return_value = False
    page.run_task.return_value = mock_task
    return page


@pytest.fixture
def editor(mock_page) -> EconomyEditor:
    return EconomyEditor(
        page=mock_page,
        file_display=MagicMock(),
        event_display=MagicMock(),
        profile_service=ProfileService(),
        unavailable_display=UnavailableDisplay(page=mock_page),
    )


def _project(tmp_path: Path, *, profiles_dir: str = "", **kwargs) -> Project:
    eco = tmp_path / "eco"
    eco.mkdir(parents=True, exist_ok=True)
    return Project(
        name="T",
        economy_dir=str(eco),
        types_dir=str(eco / "db"),
        profiles_dir=profiles_dir,
        **kwargs,
    )


def test_load_project_adds_dynamic_entities(editor, tmp_path):
    mod = tmp_path / "profiles" / "MOD"
    mod.mkdir(parents=True)
    (mod / "config.json").write_text("{}")
    project = _project(tmp_path, profiles_dir=str(tmp_path / "profiles"))

    editor.load_project(project)

    assert "MOD" in editor.available_entities
    assert editor.available_entities[0] == "Types"
    assert editor.available_entities[-1] == "MOD"


def test_load_project_dynamic_entity_strategy(editor, tmp_path):
    mod = tmp_path / "profiles" / "MOD"
    mod.mkdir(parents=True)
    (mod / "a.json").write_text("{}")
    project = _project(tmp_path, profiles_dir=str(tmp_path / "profiles"))

    editor.set_show_unhandled_editors(True)
    editor.load_project(project)

    files = editor._entities["MOD"]
    assert files["a.json"].endswith("a.json")


def test_load_project_custom_entities(editor, tmp_path):
    mod = tmp_path / "profiles" / "MOD"
    mod.mkdir(parents=True)
    (mod / "a.json").write_text("{}")
    custom = {"MOD": {"b.json": "/fake/b.json"}}
    project = _project(
        tmp_path,
        profiles_dir=str(tmp_path / "profiles"),
        custom_entities=custom,
    )

    editor.load_project(project)

    assert editor._entities["MOD"] == {"b.json": "/fake/b.json"}


def test_load_project_custom_overrides_dynamic(editor, tmp_path):
    mod = tmp_path / "profiles" / "MOD"
    mod.mkdir(parents=True)
    (mod / "a.json").write_text("{}")
    custom = {"MOD": {"user.xml": "/fake/user.xml"}}
    project = _project(
        tmp_path,
        profiles_dir=str(tmp_path / "profiles"),
        custom_entities=custom,
    )

    editor.load_project(project)

    assert editor._entities["MOD"] == {"user.xml": "/fake/user.xml"}


def test_load_project_standard_entities_not_overridden(editor, tmp_path):
    custom = {"Types": {"user.json": "/fake/user.json"}}
    project = _project(tmp_path, custom_entities=custom)

    editor.load_project(project)

    assert editor._entities["Types"] == {}


def test_load_project_no_profiles_dir(editor, tmp_path):
    project = _project(tmp_path)
    editor.load_project(project)
    assert editor.available_entities == ["Types"]
    assert editor._current_entity is not None


def test_load_project_profile_without_profiles_dir_service(editor, tmp_path):
    project = _project(tmp_path, profiles_dir=str(tmp_path / "missing"))
    editor.load_project(project)
    assert editor.available_entities == ["Types"]


def test_switch_entity_dynamic_uses_default_config(editor, tmp_path):
    mod = tmp_path / "profiles" / "MOD"
    mod.mkdir(parents=True)
    (mod / "a.json").write_text("{}")
    project = _project(tmp_path, profiles_dir=str(tmp_path / "profiles"))

    editor.set_show_unhandled_editors(True)
    editor.load_project(project)
    assert editor._current_entity == "Types"

    editor.switch_entity("MOD")
    assert editor.current_entity == "MOD"
    assert editor.current_file == "a.json"
    assert editor.entity_files == ["a.json"]


def test_switch_entity_unhandled_mod_uses_unavailable_display(editor, tmp_path):
    mod = tmp_path / "profiles" / "MOD"
    mod.mkdir(parents=True)
    (mod / "a.json").write_text("{}")
    project = _project(tmp_path, profiles_dir=str(tmp_path / "profiles"))

    editor.load_project(project)
    editor.switch_entity("MOD")

    assert editor.current_entity == "MOD"
    assert editor.current_file is None
    assert editor._entities["MOD"] == {}
    config = editor._config_for("MOD")
    assert isinstance(config.display, UnavailableDisplay)


def test_set_show_unhandled_editors_toggles_routing(editor, tmp_path):
    mod = tmp_path / "profiles" / "MOD"
    mod.mkdir(parents=True)
    (mod / "a.json").write_text("{}")
    project = _project(tmp_path, profiles_dir=str(tmp_path / "profiles"))

    editor.load_project(project)
    assert isinstance(editor._config_for("MOD").display, UnavailableDisplay)

    editor.switch_entity("MOD")
    editor.set_show_unhandled_editors(True)

    assert editor.current_entity == "MOD"
    assert editor._entities["MOD"]["a.json"].endswith("a.json")
    assert editor._config_for("MOD").display is not editor._unavailable_display

    editor.set_show_unhandled_editors(False)

    assert editor._entities["MOD"] == {}
    assert isinstance(editor._config_for("MOD").display, UnavailableDisplay)


def test_unhandled_mod_custom_entities_stay_editable(editor, tmp_path):
    mod = tmp_path / "profiles" / "MOD"
    mod.mkdir(parents=True)
    (mod / "a.json").write_text("{}")
    custom = {"MOD": {"user.json": "/fake/user.json"}}
    project = _project(
        tmp_path,
        profiles_dir=str(tmp_path / "profiles"),
        custom_entities=custom,
    )

    editor.load_project(project)

    assert editor._entities["MOD"] == {"user.json": "/fake/user.json"}
    assert editor._config_for("MOD").display is not editor._unavailable_display


def test_unhandled_switch_keeps_registered_entities_editable(editor, tmp_path):
    from custom_entities import EntityConfig, register_entity

    mod = tmp_path / "profiles" / "RegisteredMod"
    mod.mkdir(parents=True)
    (mod / "cfg.json").write_text("{}")
    register_entity("RegisteredMod", EntityConfig())
    try:
        project = _project(tmp_path, profiles_dir=str(tmp_path / "profiles"))
        editor.load_project(project)

        assert editor._config_for("RegisteredMod").display is not editor._unavailable_display
        assert isinstance(editor._entities["RegisteredMod"].get("cfg.json"), str)
    finally:
        for name in list(
            __import__("custom_entities")._CUSTOM_ENTITIES
        ):
            del __import__("custom_entities")._CUSTOM_ENTITIES[name]


def test_switch_entity_unknown_is_noop(editor, tmp_path):
    project = _project(tmp_path)
    editor.load_project(project)
    editor.switch_entity("DoesNotExist")
    assert editor.current_entity == "Types"


def test_save_current_dynamic_entity_does_not_crash(editor, tmp_path):
    mod = tmp_path / "profiles" / "MOD"
    mod.mkdir(parents=True)
    (mod / "a.json").write_text("{}")
    project = _project(tmp_path, profiles_dir=str(tmp_path / "profiles"))

    editor.set_show_unhandled_editors(True)
    editor.load_project(project)
    editor.switch_entity("MOD")
    editor.save_current()


def test_get_file_path_finds_dynamic_entity_file(editor, tmp_path):
    mod = tmp_path / "profiles" / "MOD"
    mod.mkdir(parents=True)
    (mod / "a.json").write_text("{}")
    project = _project(tmp_path, profiles_dir=str(tmp_path / "profiles"))

    editor.set_show_unhandled_editors(True)
    editor.load_project(project)
    assert editor.get_file_path("a.json").endswith("a.json")


@pytest.mark.parametrize(
    "mod_name",
    [
        "TraderX",
        "CommunityOnlineTools",
        "PermissionsFramework",
        "SpawnerBubaku",
        "AS_Mods",
    ],
)
def test_load_project_unavailable_entity_empty_files(editor, tmp_path, mod_name):
    mod = tmp_path / "profiles" / mod_name
    mod.mkdir(parents=True)
    (mod / "settings.json").write_text("{}")
    project = _project(tmp_path, profiles_dir=str(tmp_path / "profiles"))

    editor.load_project(project)

    assert mod_name in editor.available_entities
    assert editor._entities[mod_name] == {}


def test_switch_entity_unavailable_uses_unavailable_display(editor, tmp_path):
    mod = tmp_path / "profiles" / "TraderX"
    mod.mkdir(parents=True)
    (mod / "settings.json").write_text("{}")
    project = _project(tmp_path, profiles_dir=str(tmp_path / "profiles"))

    editor.load_project(project)
    editor.switch_entity("TraderX")

    assert editor.current_entity == "TraderX"
    assert editor.current_file is None
    assert editor.entity_files == []
    assert editor._unavailable_display.control.visible is True
    unavailable = editor._config_for("TraderX").display
    assert isinstance(unavailable, UnavailableDisplay)


def test_switch_entity_unavailable_display_sets_message(editor, tmp_path):
    mod = tmp_path / "profiles" / "TraderX"
    mod.mkdir(parents=True)
    (mod / "settings.json").write_text("{}")
    project = _project(tmp_path, profiles_dir=str(tmp_path / "profiles"))

    editor.load_project(project)
    editor.switch_entity("TraderX")

    assert editor._unavailable_display._entity == "TraderX"
    assert "not available" in editor._unavailable_display._message.value