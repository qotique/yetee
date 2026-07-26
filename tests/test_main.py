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


# ── ConfigService: load_files ─────────────────────────────────────────────


def test_config_load_files_returns_filenames(ce_file, mock_page):
    from services.config_service import ConfigService

    svc = ConfigService(mock_page)
    files = svc.load_files(str(ce_file))
    assert files == ["types.xml", "weapons.xml"]


def test_config_load_files_empty_returns_empty_list(ce_empty_file, mock_page):
    from services.config_service import ConfigService

    svc = ConfigService(mock_page)
    files = svc.load_files(str(ce_empty_file))
    assert files == []


def test_config_load_files_parses_real_xml(tmp_path, mock_page):
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

    svc = ConfigService(mock_page)
    files = svc.load_files(str(path))
    assert files == ["a.xml", "b.xml", "c.xml"]


# ── ConfigService: get_ce_folder / get_types_dir ──────────────────────────


def test_config_get_ce_folder(ce_file, mock_page):
    from services.config_service import ConfigService

    svc = ConfigService(mock_page)
    assert svc.get_ce_folder(str(ce_file)) == "db"


def test_config_get_types_dir(ce_file, mock_page):
    from services.config_service import ConfigService

    svc = ConfigService(mock_page)
    types_dir = svc.get_types_dir(str(ce_file))
    expected = os.path.join(os.path.dirname(str(ce_file)), "db")
    assert types_dir == expected


def test_config_get_types_dir_falls_back_to_config_dir(ce_empty_file, mock_page):
    from services.config_service import ConfigService

    svc = ConfigService(mock_page)
    types_dir = svc.get_types_dir(str(ce_empty_file))
    assert types_dir == os.path.dirname(str(ce_empty_file))


# ── ConfigService: create_type_file ───────────────────────────────────────


def test_config_create_type_file_creates_file(ce_file, mock_page, tmp_path):
    from services.config_service import ConfigService

    db_dir = tmp_path / "db"
    db_dir.mkdir()

    svc = ConfigService(mock_page)
    result = svc.create_type_file(str(ce_file), "new_types.xml")

    assert result is not None
    assert os.path.exists(result)
    assert os.path.basename(result) == "new_types.xml"

    content = Path(result).read_text(encoding="utf-8")
    assert "<types>" in content


def test_config_create_type_file_registers_in_ce(ce_file, mock_page, tmp_path):
    from services.config_service import ConfigService

    db_dir = tmp_path / "db"
    db_dir.mkdir()

    svc = ConfigService(mock_page)
    svc.create_type_file(str(ce_file), "new_types.xml")

    tree = ET.parse(str(ce_file))
    root = tree.getroot()
    ce = root.find("ce")
    assert ce is not None
    names = [fe.get("name") for fe in ce.findall("file")]
    assert "new_types.xml" in names


def test_config_create_type_file_appends_xml_ending(ce_file, mock_page, tmp_path):
    from services.config_service import ConfigService

    db_dir = tmp_path / "db"
    db_dir.mkdir()

    svc = ConfigService(mock_page)
    result = svc.create_type_file(str(ce_file), "my_types")

    assert result is not None
    assert result.endswith("my_types.xml")


# ── ConfigService: delete_type_file ───────────────────────────────────────


def test_config_delete_type_file_removes_file(ce_file, mock_page, tmp_path):
    from services.config_service import ConfigService

    db_dir = tmp_path / "db"
    db_dir.mkdir()
    type_file = db_dir / "types.xml"
    type_file.write_text("<types/>")

    svc = ConfigService(mock_page)
    result = svc.delete_type_file(str(ce_file), "types.xml")

    assert result is True
    assert not type_file.exists()


def test_config_delete_type_file_unregisters_from_ce(ce_file, mock_page, tmp_path):
    from services.config_service import ConfigService

    db_dir = tmp_path / "db"
    db_dir.mkdir()
    (db_dir / "types.xml").write_text("<types/>")

    svc = ConfigService(mock_page)
    svc.delete_type_file(str(ce_file), "types.xml")

    tree = ET.parse(str(ce_file))
    root = tree.getroot()
    ce = root.find("ce")
    assert ce is not None
    names = [fe.get("name") for fe in ce.findall("file")]
    assert "types.xml" not in names


# ── ConfigService: add_file_to_ce / remove_file_from_ce ───────────────────


def test_config_add_file_to_ce(ce_file, mock_page):
    from services.config_service import ConfigService

    tree = ET.parse(str(ce_file))
    svc = ConfigService(mock_page)
    result = svc.add_file_to_ce(tree, "test.xml")
    assert result is True

    root = tree.getroot()
    ce = root.find("ce")
    assert ce is not None
    names = [fe.get("name") for fe in ce.findall("file")]
    assert "test.xml" in names


def test_config_remove_file_from_ce(ce_file, mock_page):
    from services.config_service import ConfigService

    tree = ET.parse(str(ce_file))
    svc = ConfigService(mock_page)
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


# ── App integration ───────────────────────────────────────────────────────


def test_app_creates_service_instances(mock_page):
    from unittest.mock import patch
    with patch("flet.FilePicker"):
        from main import App
        app = App(mock_page)
        assert hasattr(app, "_config_service")
        assert hasattr(app, "_settings_service")
        assert hasattr(app, "_update_service")


def test_app_delegates_config_service(ce_file, mock_page, tmp_path):
    from unittest.mock import patch
    with patch("flet.FilePicker"):
        from main import App
        app = App(mock_page)

        svc = app._config_service
        result = svc.load_files(str(ce_file))
        assert isinstance(result, list)
        assert "types.xml" in result


def test_app_delegates_settings_service(mock_page):
    from unittest.mock import patch
    with patch("flet.FilePicker"):
        from main import App
        app = App(mock_page)
        assert app._settings_service is not None
