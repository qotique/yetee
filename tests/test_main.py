from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock
from lxml import etree as ET

import pytest


CE_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<economy>
    <ce folder="db">
        <file name="types.xml" type="types"/>
        <file name="weapons.xml" type="types"/>
    </ce>
</economy>
"""

CE_XML_NO_FILES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<economy>
</economy>
"""


@pytest.fixture
def ce_file(tmp_path):
    path = tmp_path / "cfgeconomycore.xml"
    path.write_text(CE_XML)
    return path


@pytest.fixture
def ce_empty_file(tmp_path):
    path = tmp_path / "empty.xml"
    path.write_text(CE_XML_NO_FILES)
    return path


@pytest.fixture
def mock_page():
    page = MagicMock()
    mock_task = MagicMock()
    mock_task.done.return_value = False
    page.run_task.return_value = mock_task
    return page


@pytest.fixture
def economy_dir_with_config(tmp_path):
    """Create a directory with cfgeconomycore.xml inside."""
    d = tmp_path / "mpmissions" / "chernarusplus"
    d.mkdir(parents=True)
    config = d / "cfgeconomycore.xml"
    config.write_text(CE_XML)
    return d


# ── EconomyService: new directory-based API ──────────────────────────────


def test_economy_find_config_found(economy_dir_with_config):
    from services.economy_service import EconomyService

    svc = EconomyService()
    result = svc.find_config(str(economy_dir_with_config))
    assert result is not None
    assert result.endswith("cfgeconomycore.xml")


def test_economy_find_config_not_found(tmp_path):
    from services.economy_service import EconomyService

    svc = EconomyService()
    result = svc.find_config(str(tmp_path))
    assert result is None


def test_economy_get_type_files_from_dir(economy_dir_with_config):
    from services.economy_service import EconomyService

    svc = EconomyService()
    files = svc.get_type_files(str(economy_dir_with_config))
    assert "types.xml" in files
    assert "weapons.xml" in files
    assert files["types.xml"].endswith("types.xml")
    assert "db" in files["types.xml"]  # folder=db


def test_economy_get_types_dir_from_dir(economy_dir_with_config):
    from services.economy_service import EconomyService

    svc = EconomyService()
    types_dir = svc.get_types_dir(str(economy_dir_with_config))
    expected = os.path.join(str(economy_dir_with_config), "db")
    assert types_dir == expected


def test_economy_get_types_dir_no_config(tmp_path):
    from services.economy_service import EconomyService

    svc = EconomyService()
    types_dir = svc.get_types_dir(str(tmp_path))
    assert types_dir == str(tmp_path)


def test_economy_get_type_files_no_config(tmp_path):
    from services.economy_service import EconomyService

    svc = EconomyService()
    files = svc.get_type_files(str(tmp_path))
    assert files == {}


# ── Project: backward compatibility ──────────────────────────────────────


def test_project_from_dict_migrates_config_path():
    from models.project import Project

    data = {
        "name": "Legacy",
        "config_path": "/some/dir/cfgeconomycore.xml",
        "types_dir": "/some/dir/db",
        "created_at": 1000.0,
        "last_opened": 2000.0,
    }
    project = Project.from_dict(data)
    assert project.economy_dir == "/some/dir"
    assert project.types_dir == "/some/dir/db"
    assert project.profiles_dir == ""


def test_project_to_dict_uses_economy_dir():
    from models.project import Project

    project = Project(
        name="Test",
        economy_dir="/eco",
        types_dir="/eco/db",
        profiles_dir="/profiles",
    )
    d = project.to_dict()
    assert d["economy_dir"] == "/eco"
    assert "config_path" not in d
    assert d["profiles_dir"] == "/profiles"


def test_project_custom_entities_round_trip():
    from models.project import Project

    project = Project(
        name="Test",
        economy_dir="/eco",
        types_dir="/eco/db",
        custom_entities={
            "MyMod": {
                "config.json": "/profiles/MyMod/config.json",
                "types.xml": "/profiles/MyMod/types.xml",
            }
        },
    )
    restored = Project.from_dict(project.to_dict())
    assert restored.custom_entities == project.custom_entities


def test_project_custom_entities_default_empty():
    from models.project import Project

    project = Project.from_dict(
        {"name": "Old", "economy_dir": "/eco", "types_dir": "/eco/db"}
    )
    assert project.custom_entities == {}


def test_project_custom_entities_malformed_values_skipped():
    from models.project import Project

    data = {
        "name": "Bad",
        "economy_dir": "/eco",
        "types_dir": "/eco/db",
        "custom_entities": {
            "Good": {"a.json": "/some/a.json"},
            "Bad": "not-a-dict",
        },
    }
    project = Project.from_dict(data)
    assert project.custom_entities == {"Good": {"a.json": "/some/a.json"}}


# ── ConfigService: load_files ─────────────────────────────────────────────


def test_config_load_files_returns_filenames(ce_file):
    from services.config_service import ConfigService

    svc = ConfigService()
    files = svc.load_files(str(ce_file))
    assert files == ["types.xml", "weapons.xml"]


def test_config_load_files_empty_returns_empty_list(ce_empty_file):
    from services.config_service import ConfigService

    svc = ConfigService()
    files = svc.load_files(str(ce_empty_file))
    assert files == []


def test_config_load_files_parses_real_xml(tmp_path):
    xml = """<?xml version="1.0"?>
<economy>
  <ce folder="types">
    <file name="a.xml" type="types"/>
    <file name="b.xml" type="types"/>
    <file name="c.xml" type="types"/>
  </ce>
</economy>"""
    path = tmp_path / "test.xml"
    path.write_text(xml)
    from services.config_service import ConfigService

    svc = ConfigService()
    files = svc.load_files(str(path))
    assert files == ["a.xml", "b.xml", "c.xml"]


# ── ConfigService: get_ce_folder / get_types_dir ──────────────────────────


def test_config_get_ce_folder(ce_file):
    from services.config_service import ConfigService

    svc = ConfigService()
    assert svc.get_ce_folder(str(ce_file)) == "db"


def test_config_get_types_dir(ce_file):
    from services.config_service import ConfigService

    svc = ConfigService()
    types_dir = svc.get_types_dir(str(ce_file))
    expected = os.path.join(os.path.dirname(str(ce_file)), "db")
    assert types_dir == expected


def test_config_get_types_dir_falls_back_to_config_dir(ce_empty_file):
    from services.config_service import ConfigService

    svc = ConfigService()
    types_dir = svc.get_types_dir(str(ce_empty_file))
    assert types_dir == os.path.dirname(str(ce_empty_file))


# ── ConfigService: create_type_file ───────────────────────────────────────


def test_config_create_type_file_creates_file(ce_file, tmp_path):
    from services.config_service import ConfigService

    db_dir = tmp_path / "db"
    db_dir.mkdir()

    svc = ConfigService()
    result = svc.create_type_file(str(ce_file), "new_types.xml")

    assert result is not None
    assert os.path.exists(result)
    assert os.path.basename(result) == "new_types.xml"

    content = Path(result).read_text(encoding="utf-8")
    assert "<types>" in content


def test_config_create_type_file_registers_in_ce(ce_file, tmp_path):
    from services.config_service import ConfigService

    db_dir = tmp_path / "db"
    db_dir.mkdir()

    svc = ConfigService()
    svc.create_type_file(str(ce_file), "new_types.xml")

    tree = ET.parse(str(ce_file))
    root = tree.getroot()
    ce = root.find("ce")
    assert ce is not None
    names = [fe.get("name") for fe in ce.findall("file")]
    assert "new_types.xml" in names


def test_config_create_type_file_appends_xml_ending(ce_file, tmp_path):
    from services.config_service import ConfigService

    db_dir = tmp_path / "db"
    db_dir.mkdir()

    svc = ConfigService()
    result = svc.create_type_file(str(ce_file), "my_types")

    assert result is not None
    assert result.endswith("my_types.xml")


# ── ConfigService: delete_type_file ───────────────────────────────────────


def test_config_delete_type_file_removes_file(ce_file, tmp_path):
    from services.config_service import ConfigService

    db_dir = tmp_path / "db"
    db_dir.mkdir()
    type_file = db_dir / "types.xml"
    type_file.write_text("<types/>")

    svc = ConfigService()
    result = svc.delete_type_file(str(ce_file), "types.xml")

    assert result is True
    assert not type_file.exists()


def test_config_delete_type_file_unregisters_from_ce(ce_file, tmp_path):
    from services.config_service import ConfigService

    db_dir = tmp_path / "db"
    db_dir.mkdir()
    (db_dir / "types.xml").write_text("<types/>")

    svc = ConfigService()
    svc.delete_type_file(str(ce_file), "types.xml")

    tree = ET.parse(str(ce_file))
    root = tree.getroot()
    ce = root.find("ce")
    assert ce is not None
    names = [fe.get("name") for fe in ce.findall("file")]
    assert "types.xml" not in names


# ── ConfigService: add_file_to_ce / remove_file_from_ce ───────────────────


def test_config_add_file_to_ce(ce_file):
    from services.config_service import ConfigService

    tree = ET.parse(str(ce_file))
    svc = ConfigService()
    result = svc.add_file_to_ce(tree, "test.xml")
    assert result is True

    root = tree.getroot()
    ce = root.find("ce")
    assert ce is not None
    names = [fe.get("name") for fe in ce.findall("file")]
    assert "test.xml" in names


def test_config_remove_file_from_ce(ce_file):
    from services.config_service import ConfigService

    tree = ET.parse(str(ce_file))
    svc = ConfigService()
    result = svc.remove_file_from_ce(tree, "types.xml")
    assert result is True

    root = tree.getroot()
    ce = root.find("ce")
    assert ce is not None
    names = [fe.get("name") for fe in ce.findall("file")]
    assert "types.xml" not in names


# ── SettingsService ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_settings_round_trip(mock_page):
    from services.settings_service import SettingsService

    storage: dict[str, object] = {}

    async def mock_get(key: str) -> object:
        return storage.get(key)

    async def mock_set(key: str, value: object) -> None:
        storage[key] = value

    mock_page.shared_preferences.get = mock_get
    mock_page.shared_preferences.set = mock_set

    svc = SettingsService(mock_page)

    await svc.save_setting("theme", "DARK")
    settings = await svc.load_settings()
    assert settings["theme"] == "DARK"

    await svc.save_setting("language", "Русский")
    settings = await svc.load_settings()
    assert settings["language"] == "Русский"

    await svc.save_setting("check_updates", False)
    settings = await svc.load_settings()
    assert settings["check_updates"] is False

    await svc.save_setting("show_unhandled_mod_editors", True)
    settings = await svc.load_settings()
    assert settings["show_unhandled_mod_editors"] is True


# ── App integration ───────────────────────────────────────────────────────


def test_app_creates_service_instances(mock_page):
    from unittest.mock import patch, MagicMock

    with patch("flet.FilePicker"):
        from main import App
        from services.config_service import ConfigService
        from services.entertainment_service import EntertainmentService
        from services.settings_service import SettingsService
        from services.update_service import UpdateService

        config_service = ConfigService()
        settings_service = SettingsService(mock_page)
        update_service = UpdateService(mock_page)
        entertainment_service = EntertainmentService()
        project_service = MagicMock()
        economy_editor = MagicMock()
        app = App(
            mock_page,
            config_service,
            settings_service,
            update_service,
            entertainment_service,
            project_service,
            economy_editor,
        )
        assert hasattr(app, "_config_service")
        assert hasattr(app, "_settings_service")
        assert hasattr(app, "_update_service")
        assert hasattr(app, "_entertainment_service")
        assert hasattr(app, "_project_service")
        assert hasattr(app, "_economy_editor")


def test_app_delegates_config_service(ce_file, mock_page, tmp_path):
    from unittest.mock import patch, MagicMock

    with patch("flet.FilePicker"):
        from main import App
        from services.config_service import ConfigService
        from services.entertainment_service import EntertainmentService
        from services.settings_service import SettingsService
        from services.update_service import UpdateService

        config_service = ConfigService()
        settings_service = SettingsService(mock_page)
        update_service = UpdateService(mock_page)
        entertainment_service = EntertainmentService()
        project_service = MagicMock()
        economy_editor = MagicMock()
        app = App(
            mock_page,
            config_service,
            settings_service,
            update_service,
            entertainment_service,
            project_service,
            economy_editor,
        )

        svc = app._config_service
        result = svc.load_files(str(ce_file))
        assert isinstance(result, list)
        assert "types.xml" in result


def test_app_delegates_settings_service(mock_page):
    from unittest.mock import patch, MagicMock

    with patch("flet.FilePicker"):
        from main import App
        from services.config_service import ConfigService
        from services.entertainment_service import EntertainmentService
        from services.settings_service import SettingsService
        from services.update_service import UpdateService

        config_service = ConfigService()
        settings_service = SettingsService(mock_page)
        update_service = UpdateService(mock_page)
        entertainment_service = EntertainmentService()
        project_service = MagicMock()
        economy_editor = MagicMock()
        app = App(
            mock_page,
            config_service,
            settings_service,
            update_service,
            entertainment_service,
            project_service,
            economy_editor,
        )
        assert app._settings_service is not None


def test_app_injects_profile_service(mock_page):
    from unittest.mock import patch, MagicMock

    with patch("flet.FilePicker"):
        from main import App
        from services.config_service import ConfigService
        from services.entertainment_service import EntertainmentService
        from services.profile_service import ProfileService
        from services.settings_service import SettingsService
        from services.update_service import UpdateService

        config_service = ConfigService()
        settings_service = SettingsService(mock_page)
        update_service = UpdateService(mock_page)
        entertainment_service = EntertainmentService()
        project_service = MagicMock()
        economy_editor = MagicMock()
        profile_service = ProfileService()
        app = App(
            mock_page,
            config_service,
            settings_service,
            update_service,
            entertainment_service,
            project_service,
            economy_editor,
            profile_service=profile_service,
        )
        assert app._profile_service is profile_service


def test_app_create_project_default_profile_service(mock_page):
    from unittest.mock import MagicMock

    from main import App
    from services.config_service import ConfigService
    from services.entertainment_service import EntertainmentService
    from services.settings_service import SettingsService
    from services.update_service import UpdateService

    config_service = ConfigService()
    settings_service = SettingsService(mock_page)
    update_service = UpdateService(mock_page)
    entertainment_service = EntertainmentService()
    project_service = MagicMock()
    economy_editor = MagicMock()
    app = App(
        mock_page,
        config_service,
        settings_service,
        update_service,
        entertainment_service,
        project_service,
        economy_editor,
    )
    assert app._profile_service is not None


def test_app_new_project_dialog_has_no_custom_entities_button(mock_page):
    from unittest.mock import patch

    from main import App
    from services.config_service import ConfigService
    from services.entertainment_service import EntertainmentService
    from services.settings_service import SettingsService
    from services.update_service import UpdateService

    with patch("flet.FilePicker"):
        config_service = ConfigService()
        settings_service = SettingsService(mock_page)
        update_service = UpdateService(mock_page)
        entertainment_service = EntertainmentService()
        project_service = MagicMock()
        economy_editor = MagicMock()
        app = App(
            mock_page,
            config_service,
            settings_service,
            update_service,
            entertainment_service,
            project_service,
            economy_editor,
        )
        app._show_new_project_dialog()
        dialog = mock_page.show_dialog.call_args.args[0]
        content = dialog.content
        import flet as ft

        texts = []
        for c in content.controls:
            if isinstance(c, ft.Text):
                texts.append(c.value)
            elif isinstance(c, ft.Row):
                texts.extend(
                    child.content for child in c.controls if hasattr(child, "content")
                )
        assert "Add Custom Entity..." not in texts
        assert "No custom entities yet." not in texts


def test_preload_delegates_to_project_flow(mock_page):
    from unittest.mock import MagicMock

    from main import App

    economy_editor = MagicMock()
    economy_editor.settings_display = MagicMock()
    app = App(
        mock_page,
        MagicMock(),
        MagicMock(),
        MagicMock(),
        MagicMock(),
        MagicMock(),
        economy_editor,
    )
    project = MagicMock()
    calls: dict[str, object] = {}

    def fake_preload(p: object, *, confirm: bool) -> None:
        calls["project"] = p
        calls["confirm"] = confirm

    app.project_flow.preload_profile_files = fake_preload
    app._preload_profile_files(project, confirm=True)
    assert calls == {"project": project, "confirm": True}


def test_unhandled_editors_switch_saves_setting_and_routes(mock_page):
    import asyncio

    from main import App

    settings_service = MagicMock()
    economy_editor = MagicMock()
    economy_editor.settings_display = MagicMock()
    app = App(
        mock_page,
        MagicMock(),
        settings_service,
        MagicMock(),
        MagicMock(),
        MagicMock(),
        economy_editor,
    )

    async def run():
        await app._on_unhandled_editors_change(
            type(
                "E",
                (),
                {"control": type("C", (), {"value": True})()},
            )()
        )

    asyncio.run(run())

    assert app.show_unhandled_mod_editors is True
    assert app.settings_manager.show_unhandled_mod_editors is True
    economy_editor.set_show_unhandled_editors.assert_called_once_with(True)
    settings_service.save_setting.assert_called_once_with(
        "show_unhandled_mod_editors", True
    )


def test_app_wires_editor_save_callbacks(mock_page):
    from unittest.mock import MagicMock

    from main import App

    editor = MagicMock()
    editor.settings_display = None
    editor.form_display = None
    app = App(
        mock_page,
        MagicMock(),
        MagicMock(),
        MagicMock(),
        MagicMock(),
        MagicMock(),
        editor,
    )
    assert editor.file_display.on_saved == app.remote_flow.on_local_saved
    assert editor.event_display.on_saved == app.remote_flow.on_local_saved


def test_app_shell_widgets_bound(mock_page):
    from unittest.mock import MagicMock

    from main import App

    editor = MagicMock()
    editor.settings_display = None
    editor.form_display = None
    app = App(
        mock_page,
        MagicMock(),
        MagicMock(),
        MagicMock(),
        MagicMock(),
        MagicMock(),
        editor,
    )
    shell = app.shell
    assert shell.save_btn.on_click == app._on_save
    assert shell.project_dropdown.on_select == app.project_flow.on_project_switch
    assert shell.entity_dropdown.on_select == app.project_flow.on_entity_switch
    assert shell.refresh_btn.on_click == app.remote_flow.on_refresh_project
    assert (
        shell.start_open_project_btn.on_click
        == app.project_flow.show_open_project_dialog
    )
