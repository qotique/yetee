from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import flet as ft
import pytest

from ui.form_display import FormDisplay
from models.form_schema import (
    FormDict,
    FormField,
    FormGrid,
    FormList,
    FormGroup,
    FormSchema,
    build_auto_form_schema,
    get_form_schema_for_path,
    humanize_key,
    register_form_folder_schema,
    register_form_schema,
)
from models.field_def import FieldType
from repository.settings_repository import JsonSettingsRepository


class TestHumanizeKey:
    def test_camel_case(self):
        assert humanize_key("ServerUpdateRateLimit") == "Server Update Rate Limit"

    def test_m_version(self):
        assert humanize_key("m_Version") == "Version"

    def test_localized(self):
        assert humanize_key("#STR_EXPANSION_MARKET_CATEGORY_FOOD") == (
            "Expansion Market Category Food"
        )

    def test_underscores(self):
        assert humanize_key("max_price") == "Max Price"


class TestBuildAutoFormSchema:
    def test_flat_object_types(self):
        doc = {"Name": "x", "Count": 5, "Ratio": 1.5, "Enabled": True, "Toggle": 1}
        schema = build_auto_form_schema(doc)
        by_key = {f.key: f for f in schema.fields}
        assert by_key["Count"].type == FieldType.INT
        assert by_key["Ratio"].type == FieldType.FLOAT
        assert by_key["Enabled"].type == FieldType.BOOL
        assert by_key["Toggle"].type == FieldType.TOGGLE
        assert by_key["Name"].type == FieldType.TEXT

    def test_scalar_dict_becomes_dict(self):
        doc = {"Weapons": {"Damage": 5}}
        schema = build_auto_form_schema(doc)
        assert schema.dicts
        assert schema.dicts[0].key == "Weapons"
        assert schema.dicts[0].value_type == FieldType.INT

    def test_deep_nested_object_becomes_group(self):
        doc = {"Server": {"Limits": {"Max": 5}}}
        schema = build_auto_form_schema(doc)
        assert schema.groups
        group = schema.groups[0]
        assert group.key == "Server"
        assert [d.key for d in group.schema.dicts] == ["Limits"]

    def test_array_of_objects_becomes_grid(self):
        doc = {"Items": [{"ClassName": "A", "Price": 5}]}
        schema = build_auto_form_schema(doc)
        assert schema.grids
        grid = schema.grids[0]
        assert {c.key for c in grid.columns} == {"ClassName", "Price"}
        assert {c.key: c.type for c in grid.columns}["Price"] == FieldType.INT

    def test_scalar_list_becomes_list(self):
        doc = {"Names": ["a", "b"]}
        schema = build_auto_form_schema(doc)
        assert schema.lists
        assert schema.lists[0].key == "Names"

    def test_scalar_dict_becomes_dict(self):
        doc = {"Items": {"AKM": 1, "M4": 0}}
        schema = build_auto_form_schema(doc)
        assert schema.dicts
        assert schema.dicts[0].key == "Items"
        assert schema.dicts[0].value_type == FieldType.TOGGLE

    def test_doc_array_uses_first_item_and_name_key(self):
        doc = [{"DisplayName": "Trader A", "Id": 1}]
        schema = build_auto_form_schema(doc)
        assert schema.name_key == "DisplayName"
        assert [f.key for f in schema.fields] == ["DisplayName", "Id"]

    def test_flat_object_array_uses_columns(self):
        doc = {"Items": [{"ClassName": "A", "Chance": 1.0}]}
        schema = build_auto_form_schema(doc)
        grid = schema.grids[0]
        assert grid.item_schema is None
        assert {c.key for c in grid.columns} == {"ClassName", "Chance"}

    def test_nested_object_array_uses_item_schema(self):
        doc = {
            "InventoryAttachments": [
                {
                    "SlotName": "Body",
                    "Items": [{"ClassName": "A", "Quantity": {"Min": 0.0}}],
                }
            ]
        }
        schema = build_auto_form_schema(doc)
        grid = schema.grids[0]
        assert grid.key == "InventoryAttachments"
        assert grid.item_schema is not None
        assert [f.key for f in grid.item_schema.fields] == ["SlotName"]
        nested = [g for g in grid.item_schema.grids if g.key == "Items"][0]
        assert nested.item_schema is not None
        assert [f.key for f in nested.item_schema.fields] == ["ClassName"]

    def test_loadout_like_recursion(self):
        doc = {
            "ClassName": "Bandit",
            "InventoryAttachments": [
                {
                    "SlotName": "Legs",
                    "Items": [
                        {
                            "ClassName": "Pants",
                            "Quantity": {"Min": 0.0, "Max": 0.0},
                            "InventoryCargo": [
                                {
                                    "ClassName": "Can",
                                    "InventoryCargo": [{"ClassName": "Bullet"}],
                                }
                            ],
                        }
                    ],
                }
            ],
        }
        schema = build_auto_form_schema(doc)
        ia = [g for g in schema.grids if g.key == "InventoryAttachments"][0]
        assert ia.item_schema is not None
        slot = ia.item_schema
        assert [f.key for f in slot.fields] == ["SlotName"]
        items_grid = [g for g in slot.grids if g.key == "Items"][0]
        assert items_grid.item_schema is not None
        item = items_grid.item_schema
        assert [d.key for d in item.dicts] == ["Quantity"]
        cargo = [g for g in item.grids if g.key == "InventoryCargo"][0]
        assert cargo.item_schema is not None
        assert [f.key for f in cargo.item_schema.fields] == ["ClassName"]


class TestFormSchemaRegistry:
    def test_path_based_lookup_folder(self):
        register_form_folder_schema(
            "X", "market/traders", FormSchema(name_key="DisplayName")
        )
        schema = get_form_schema_for_path(
            "X", "mpmissions/chernarusplus/expansion/market/traders/trader.json"
        )
        assert schema is not None
        assert schema.name_key == "DisplayName"

    def test_path_based_lookup_basename(self):
        register_form_schema(
            "X",
            "CoreSettings.json",
            FormSchema(fields=(FormField("m_Version", "Version"),)),
        )
        schema = get_form_schema_for_path("X", "expansion/settings/CoreSettings.json")
        assert schema is not None
        assert schema.fields[0].key == "m_Version"

    def test_folder_takes_precedence_by_path(self):
        register_form_schema("Y", "a.json", FormSchema(name_key="FileSchema"))
        register_form_folder_schema("Y", "folder", FormSchema(name_key="FolderSchema"))
        schema = get_form_schema_for_path("Y", "x/folder/a.json")
        assert schema.name_key == "FileSchema"


class TestFormDisplay:
    @pytest.fixture
    def page(self):
        page = MagicMock()
        page.theme = None
        page.dark_theme = None
        page.on_keyboard_event = None
        return page

    @pytest.fixture
    def display(self, page) -> FormDisplay:
        return FormDisplay(page=page, json_repo=JsonSettingsRepository())

    def _write(self, tmp_path: Path, name: str, doc: object) -> str:
        path = tmp_path / name
        path.write_text(json.dumps(doc))
        return str(path)

    def test_load_flat_object_renders_fields(self, display, tmp_path):
        path = self._write(
            tmp_path, "settings.json", {"m_Version": 9, "EnableLamps": 1, "Name": "srv"}
        )
        display.set_entity("Expansion Settings")
        display.load_file(path)
        assert display._schema.fields
        assert display.control.visible
        assert display._master_mode == "none"

    def test_master_files_mode(self, display, tmp_path):
        display.set_entity("Expansion Settings")
        display.set_files(
            {
                "CoreSettings.json": self._write(
                    tmp_path, "CoreSettings.json", {"m_Version": 9}
                ),
                "GeneralSettings.json": self._write(
                    tmp_path, "GeneralSettings.json", {"m_Version": 16}
                ),
            }
        )
        display.load_file(next(iter(display._files.values())))
        assert display._master_mode == "files"
        assert len(display._master.controls) == 2

    def test_reload_within_same_entity_reuses_master_tree(self, display, tmp_path):
        display.set_entity("Expansion Settings")
        display.set_files(
            {
                "CoreSettings.json": self._write(
                    tmp_path, "CoreSettings.json", {"m_Version": 9}
                ),
                "GeneralSettings.json": self._write(
                    tmp_path, "GeneralSettings.json", {"m_Version": 16}
                ),
                "SmithingSettings.json": self._write(
                    tmp_path, "SmithingSettings.json", {"m_Version": 1}
                ),
            }
        )
        first = next(iter(display._files.values()))
        display.load_file(first)
        assert display._master_mode == "files"
        controls_before = display._master.controls
        assert len(controls_before) == 3
        row = display._master_rows[display._current_label]
        assert row.bgcolor == ft.Colors.SECONDARY_CONTAINER
        second = next(
            v for k, v in display._files.items() if k != display._current_label
        )
        display.load_file(second)
        assert display._master.controls is controls_before
        assert display._current_label != ""
        assert (
            display._master_rows[display._current_label].bgcolor
            == ft.Colors.SECONDARY_CONTAINER
        )
        assert display._master_rows[first.split("/")[-1]].bgcolor is None

    def test_master_files_grouped_by_category(self, display, tmp_path):
        display.set_entity("ExpansionMod")
        display.set_files(
            {
                "Settings/CoreSettings.json": self._write(
                    tmp_path, "CoreSettings.json", {"m_Version": 9}
                ),
                "Settings/GeneralSettings.json": self._write(
                    tmp_path, "GeneralSettings.json", {"m_Version": 16}
                ),
                "Loadouts/BanditLoadout.json": self._write(
                    tmp_path, "BanditLoadout.json", {"ClassName": "Bandit"}
                ),
            }
        )
        display.load_file(next(iter(display._files.values())))
        assert display._master_mode == "files"
        tiles = [c for c in display._master.controls if isinstance(c, ft.ExpansionTile)]
        assert [t.title.value for t in tiles] == ["Loadouts", "Settings"]
        loadout_rows = [
            row.content.value
            for row in tiles[0].controls
            if isinstance(row, ft.Container)
        ]
        assert loadout_rows == ["BanditLoadout.json"]
        settings_rows = [
            row.content.value
            for row in tiles[1].controls
            if isinstance(row, ft.Container)
        ]
        assert settings_rows == ["CoreSettings.json", "GeneralSettings.json"]

    def test_master_files_subcategories(self, display, tmp_path):
        display.set_entity("ExpansionMod")
        display.set_files(
            {
                "AI/FSM/fight.json": self._write(
                    tmp_path, "fight.json", {"m_Version": 1}
                ),
                "AI/LootDrops/zone.json": self._write(
                    tmp_path, "zone.json", {"m_Version": 1}
                ),
                "Quests/NPCs/bob.json": self._write(
                    tmp_path, "bob.json", {"m_Version": 1}
                ),
            }
        )
        display.load_file(next(iter(display._files.values())))
        assert display._master_mode == "files"
        tiles = [c for c in display._master.controls if isinstance(c, ft.ExpansionTile)]
        assert [t.title.value for t in tiles] == ["AI", "Quests"]
        ai_sub = [c for c in tiles[0].controls if isinstance(c, ft.ExpansionTile)]
        assert [t.title.value for t in ai_sub] == ["FSM", "LootDrops"]

    def test_category_add_button_only_in_create_categories(self, display, tmp_path):
        display.set_entity("ExpansionMod")
        display.set_files(
            {
                "Settings/CoreSettings.json": self._write(
                    tmp_path, "CoreSettings.json", {"m_Version": 9}
                ),
                "Loadouts/BanditLoadout.json": self._write(
                    tmp_path, "BanditLoadout.json", {"ClassName": "Bandit"}
                ),
                "Quests/NPCs/bob.json": self._write(
                    tmp_path, "bob.json", {"ClassName": "bob"}
                ),
                "Quests/Objectives/AICamp/obj.json": self._write(
                    tmp_path, "obj.json", {"ClassName": "obj"}
                ),
            }
        )
        display.load_file(next(iter(display._files.values())))
        by_key = {t.title.value: t for t in display._master.controls}
        loadout_tile = by_key["Loadouts"]
        add_rows = [c for c in loadout_tile.controls if isinstance(c, ft.TextButton)]
        assert len(add_rows) == 1
        settings_tile = by_key["Settings"]
        assert not [c for c in settings_tile.controls if isinstance(c, ft.TextButton)]
        quests_sub = {
            t.title.value: t
            for t in by_key["Quests"].controls
            if isinstance(t, ft.ExpansionTile)
        }
        assert [c for c in quests_sub["NPCs"].controls if isinstance(c, ft.TextButton)]
        assert [
            c for c in quests_sub["Objectives"].controls if isinstance(c, ft.TextButton)
        ]

    def test_category_add_templates_from_subdir_fallback(self, display, page, tmp_path):
        deep = tmp_path / "Quests" / "Objectives" / "AICamp"
        deep.mkdir(parents=True)
        sibling = deep / "Objective_AIC_1.json"
        sibling.write_text(json.dumps([{"ClassName": "C", "Min": 1}]))
        display.set_entity("ExpansionMod")
        display.set_files(
            {"Quests/Objectives/AICamp/Objective_AIC_1.json": str(sibling)}
        )

        display._on_category_add(("Quests", "Objectives"))
        dialog = page.show_dialog.call_args[0][0]
        dialog.content.controls[1].value = "MyObjective.json"
        dialog.actions[1].on_click(None)

        target = tmp_path / "Quests" / "Objectives" / "MyObjective.json"
        assert target.exists()
        assert json.loads(target.read_text()) == [{"ClassName": "", "Min": 0}]

    def test_master_file_click_uses_label(self, display, tmp_path):
        display.set_entity("Expansion Settings")
        display.set_files(
            {
                "Settings/CoreSettings.json": self._write(
                    tmp_path, "CoreSettings.json", {"m_Version": 9}
                ),
                "Settings/GeneralSettings.json": self._write(
                    tmp_path, "GeneralSettings.json", {"m_Version": 16}
                ),
            }
        )
        display.load_file(next(iter(display._files.values())))
        calls: list[str] = []
        display.on_file_select = lambda label: calls.append(label)
        tile = display._master.controls[0]
        row = tile.controls[1]
        display._on_file_master_click(MagicMock(control=row))
        assert calls == ["Settings/GeneralSettings.json"]

    def test_array_doc_uses_item_master(self, display, tmp_path):
        path = self._write(
            tmp_path,
            "traders.json",
            [{"DisplayName": "A", "Id": 1}, {"DisplayName": "B", "Id": 2}],
        )
        display.set_entity("Expansion Market")
        display.load_file(path)
        assert display._master_mode == "items"
        labels = [c.content.value for c in display._master.controls]
        assert labels == ["A", "B"]

    def test_root_array_in_files_mode_renders_editable(self, display, tmp_path):
        path = self._write(
            tmp_path,
            "Example.json",
            [
                {"ClassName": "AKM", "Chance": 0.5},
                {"ClassName": "M4", "Chance": 0.3},
            ],
        )
        other = self._write(tmp_path, "other.json", {"m_Version": 1})
        display.set_entity("ExpansionMod")
        display.set_files(
            {"AI/LootDrops/Example.json": path, "Settings/CoreSettings.json": other}
        )
        display.load_file(path)
        assert display._master_mode == "files"
        tiles = [c for c in display._detail.controls if isinstance(c, ft.ExpansionTile)]
        assert len(tiles) == 2
        labels = [t.title.controls[0].content.value for t in tiles]
        assert labels == ["AKM", "M4"]
        assert any(
            isinstance(c, ft.TextButton) and c.content == "Add item"
            for c in display._detail.controls
        )

    def test_root_array_add_item(self, display, tmp_path):
        path = self._write(tmp_path, "Example.json", [{"ClassName": "AKM"}])
        other = self._write(tmp_path, "other.json", {"m_Version": 1})
        display.set_entity("ExpansionMod")
        display.set_files(
            {"AI/LootDrops/Example.json": path, "Settings/CoreSettings.json": other}
        )
        display.load_file(path)
        display._on_root_add()
        assert len(display._doc) == 2
        assert display._doc[1] == {}
        display._on_root_delete(0)
        assert len(display._doc) == 1
        assert display._doc[0] == {}
        display.save_file()
        saved = json.loads(Path(path).read_text())
        assert saved == [{}]

    def test_save_round_trip_coerces_types(self, display, tmp_path):
        path = self._write(
            tmp_path,
            "settings.json",
            {"m_Version": 9, "EnableLamps": 1, "Items": {"AKM": 1}},
        )
        display.set_entity("Expansion Settings")
        display.load_file(path)
        display._doc["EnableLamps"] = 0
        display._doc["Items"]["AKM"] = "3"
        display.save_file()
        saved = json.loads(Path(path).read_text())
        assert saved["EnableLamps"] == 0
        assert saved["Items"]["AKM"] == 3
        assert saved["m_Version"] == 9

    def test_save_fires_on_saved(self, display, tmp_path):
        path = self._write(tmp_path, "settings.json", {"x": 1})
        display.set_entity("E")
        display.load_file(path)
        fired = []
        display.on_saved = lambda: fired.append(True)
        display.save_file()
        assert fired == [True]

    def test_toggle_widget_is_checkbox(self, display, tmp_path):
        path = self._write(tmp_path, "s.json", {"Enable": 1})
        display.set_entity("E")
        display.load_file(path)
        detail = display._detail.controls
        checkbox = detail[0].controls[1].content.content
        assert isinstance(checkbox, ft.Checkbox)
        assert checkbox.value is True

    def test_int_field_widget_numeric(self, display, tmp_path):
        path = self._write(tmp_path, "s.json", {"Count": 5})
        display.set_entity("E")
        display.load_file(path)
        widget = display._detail.controls[0].controls[1].content
        assert isinstance(widget, ft.TextField)
        assert widget.keyboard_type == ft.KeyboardType.NUMBER
        assert widget.value == "5"

    def test_clear_resets_state(self, display, tmp_path):
        path = self._write(tmp_path, "s.json", {"x": 1})
        display.set_entity("E")
        display.load_file(path)
        display.clear()
        assert not display.control.visible
        assert display._doc is None

    def test_load_failure_sets_status(self, display, tmp_path):
        missing = str(tmp_path / "nope.json")
        display.set_entity("E")
        import asyncio

        asyncio.run(display.load_file_async(missing))
        assert "Error" in display._status.value

    def test_category_add_creates_file(self, display, page, tmp_path):
        category = tmp_path / "AI" / "LootDrops"
        category.mkdir(parents=True)
        sibling = category / "Example.json"
        sibling.write_text(
            json.dumps([{"ClassName": "I_A", "Chance": 0.5, "Ok": True}])
        )
        display.set_entity("ExpansionMod")
        display.set_files({"AI/LootDrops/Example.json": str(sibling)})
        created = []
        display.on_file_create = lambda label, path: created.append((label, path))

        display._on_category_add(("AI", "LootDrops"))
        page.show_dialog.assert_called_once()
        dialog = page.show_dialog.call_args[0][0]
        dialog.content.controls[1].value = "MyDrop.json"
        dialog.actions[1].on_click(None)

        target = category / "MyDrop.json"
        assert target.exists()
        assert json.loads(target.read_text()) == [
            {"ClassName": "", "Chance": 0, "Ok": False}
        ]
        assert created == [("AI/LootDrops/MyDrop.json", str(target))]
        assert display._files["AI/LootDrops/MyDrop.json"] == str(target)
        assert display._current_label == "AI/LootDrops/MyDrop.json"
        page.pop_dialog.assert_called()

    def test_category_add_duplicate_name_sets_status(self, display, page, tmp_path):
        category = tmp_path / "AI" / "LootDrops"
        category.mkdir(parents=True)
        sibling = category / "Example.json"
        sibling.write_text(json.dumps([{"ClassName": "I_A"}]))
        display.set_entity("ExpansionMod")
        display.set_files({"AI/LootDrops/Example.json": str(sibling)})

        display._on_category_add(("AI", "LootDrops"))
        dialog = page.show_dialog.call_args[0][0]
        dialog.content.controls[1].value = "Example.json"
        dialog.actions[1].on_click(None)

        assert "Already exists" in display._status.value
        assert len(display._files) == 1

    def test_category_add_walks_up_to_category_dir(self, display, page, tmp_path):
        deep = tmp_path / "Quests" / "Objectives" / "AICamp"
        deep.mkdir(parents=True)
        sibling = deep / "Objective_AIC_1.json"
        sibling.write_text(json.dumps([{"ClassName": "X"}]))
        display.set_entity("ExpansionMod")
        display.set_files(
            {"Quests/Objectives/AICamp/Objective_AIC_1.json": str(sibling)}
        )

        display._on_category_add(("Quests", "Objectives"))
        dialog = page.show_dialog.call_args[0][0]
        dialog.content.controls[1].value = "MyObjective.json"
        dialog.actions[1].on_click(None)

        target = tmp_path / "Quests" / "Objectives" / "MyObjective.json"
        assert target.exists()
        assert display._current_label == "Quests/Objectives/MyObjective.json"
