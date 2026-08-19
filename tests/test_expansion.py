from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from custom_entities import _CUSTOM_ENTITIES, get_columns, get_renderer
from expansion import register_entity  # noqa: F401  (registers at import)
from models.field_def import FieldType
from models.project import Project
from services.economy_service import EconomyService
from services.profile_service import ProfileService
from unavailable_display import UnavailableDisplay
from ui.economy_editor import EconomyEditor


class TestExpansionRegistry:
    def test_profile_entity_registered(self):
        assert "ExpansionMod" in _CUSTOM_ENTITIES
        assert "Expansion Settings" in _CUSTOM_ENTITIES
        assert "Expansion Market" in _CUSTOM_ENTITIES
        assert "Expansion Quests" in _CUSTOM_ENTITIES
        assert "Expansion AI" in _CUSTOM_ENTITIES

    def test_profile_settings_renderer_json(self):
        assert get_renderer("ExpansionMod", "CoreSettings.json") == "json"

    def test_trader_folder_columns(self):
        cols = get_columns(
            "Expansion Market",
            "mpmissions/chernarusplus/expansion/market/traders/trader.json",
        )
        by_key = {fd.key: fd for fd in cols}
        assert by_key["DisplayName"].type == FieldType.TEXT
        assert by_key["MinRequiredReputation"].type == FieldType.INT
        assert by_key["TraderIcon"].type == FieldType.SINGLE_NAMED
        assert by_key["TraderIcon"].options
        assert "0" not in [c.key for c in cols if c.key == "m_Version"]

    def test_category_folder_columns(self):
        cols = get_columns(
            "Expansion Market",
            "mpmissions/chernarusplus/expansion/market/categories/cat.json",
        )
        by_key = {fd.key: fd for fd in cols}
        assert by_key["Icon"].type == FieldType.SINGLE_NAMED
        assert by_key["InitStockPercent"].type == FieldType.FLOAT

    def test_ai_settings_columns_float(self):
        cols = get_columns(
            "Expansion AI",
            "mpmissions/chernarusplus/expansion/ai/settings/AISettings.json",
        )
        by_key = {fd.key: fd for fd in cols}
        assert by_key["AccuracyMin"].type == FieldType.FLOAT

    def test_quest_settings_columns_int(self):
        cols = get_columns(
            "Expansion Quests",
            "mpmissions/chernarusplus/expansion/quests/Settings/QuestSettings.json",
        )
        by_key = {fd.key: fd for fd in cols}
        assert by_key["m_Version"].type == FieldType.INT

    def test_unknown_expansion_file_default_json(self):
        assert get_renderer("Expansion Market", "market/whatever.json") == "json"


class TestExpansionDiscovery:
    def _make_expansion(self, tmp_path: Path) -> Path:
        eco = tmp_path / "eco"
        settings = eco / "expansion" / "settings"
        settings.mkdir(parents=True)
        (settings / "BaseBuildingSettings.json").write_text("{}")
        traders = eco / "expansion" / "market" / "traders"
        traders.mkdir(parents=True)
        (traders / "trader.json").write_text("{}")
        (eco / "expansion" / "unknown.bin").write_text("x")
        return eco

    def test_get_expansion_files_groups_by_area(self, tmp_path):
        eco = self._make_expansion(tmp_path)
        files = EconomyService().get_expansion_files(str(eco))

        assert "Mission/settings/BaseBuildingSettings.json" in files
        assert "Mission/market/traders/trader.json" in files

    def test_get_expansion_files_missing_dir(self, tmp_path):
        files = EconomyService().get_expansion_files(str(tmp_path / "nope"))
        assert files == {}

    def test_get_expansion_files_rest_area(self, tmp_path):
        eco = tmp_path / "eco"
        rest = eco / "expansion" / "misc"
        rest.mkdir(parents=True)
        (rest / "x.json").write_text("{}")
        files = EconomyService().get_expansion_files(str(eco))
        assert "Mission/misc/x.json" in files


class TestLoadProjectExpansion:
    @pytest.fixture
    def mock_page(self):
        page = MagicMock()
        page.theme = None
        page.dark_theme = None
        page.on_keyboard_event = None
        mock_task = MagicMock()
        mock_task.done.return_value = False
        page.run_task.return_value = mock_task
        return page

    @pytest.fixture
    def editor(self, mock_page) -> EconomyEditor:
        return EconomyEditor(
            page=mock_page,
            file_display=MagicMock(),
            event_display=MagicMock(),
            profile_service=ProfileService(),
            unavailable_display=UnavailableDisplay(page=mock_page),
        )

    def test_load_project_adds_expansion_entities(self, editor, tmp_path):
        eco = tmp_path / "eco"
        settings = eco / "expansion" / "settings"
        settings.mkdir(parents=True)
        (settings / "BaseBuildingSettings.json").write_text("{}")
        project = Project(
            name="T",
            economy_dir=str(eco),
            types_dir=str(eco / "db"),
            profiles_dir="",
        )

        editor.load_project(project)

        assert "Expansion Settings" not in editor.available_entities
        files = editor._entities["ExpansionMod"]
        assert "Mission/settings/BaseBuildingSettings.json" in files
        assert files["Mission/settings/BaseBuildingSettings.json"].endswith(
            "BaseBuildingSettings.json"
        )

    def test_load_project_no_expansion(self, editor, tmp_path):
        eco = tmp_path / "eco"
        eco.mkdir(parents=True)
        project = Project(
            name="T",
            economy_dir=str(eco),
            types_dir=str(eco / "db"),
            profiles_dir="",
        )

        editor.load_project(project)

        assert "ExpansionMod" not in editor.available_entities

    def test_load_project_expansion_settings_uses_settings_display(
        self, editor, tmp_path
    ):
        eco = tmp_path / "eco"
        settings = eco / "expansion" / "settings"
        settings.mkdir(parents=True)
        (settings / "BaseBuildingSettings.json").write_text("{}")
        project = Project(
            name="T",
            economy_dir=str(eco),
            types_dir=str(eco / "db"),
            profiles_dir="",
        )

        editor.load_project(project)
        editor.switch_entity("ExpansionMod")

        assert editor.current_entity == "ExpansionMod"
        assert editor.current_file == "Mission/settings/BaseBuildingSettings.json"

    def test_load_project_expansion_does_not_override_builtin(self, editor, tmp_path):
        eco = tmp_path / "eco"
        settings = eco / "expansion" / "settings"
        settings.mkdir(parents=True)
        (settings / "BaseBuildingSettings.json").write_text("{}")
        (eco / "Types.json").write_text("{}")
        project = Project(
            name="T",
            economy_dir=str(eco),
            types_dir=str(eco / "db"),
            profiles_dir="",
            custom_entities={"Types": {"user.xml": "/fake/user.xml"}},
        )

        editor.load_project(project)

        assert "ExpansionMod" in editor.available_entities
        assert editor._entities["Types"] == {}
