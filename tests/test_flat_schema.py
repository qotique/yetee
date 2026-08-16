from __future__ import annotations

import json

import pytest

from models.field_def import FieldDef, FieldType
from repository.settings_repository import JsonSettingsRepository, XmlSettingsRepository


def _defs() -> tuple[FieldDef, ...]:
    return (
        FieldDef("m_Version", "Version", FieldType.INT, width=90),
        FieldDef("ServerUpdateRateLimit", "Rate", FieldType.FLOAT, width=140),
        FieldDef("Enabled", "Enabled", FieldType.BOOL, width=110),
        FieldDef("DisplayName", "Display Name", FieldType.TEXT, width=200),
    )


@pytest.fixture
def json_repo() -> JsonSettingsRepository:
    return JsonSettingsRepository()


class TestFlatSchemaParse:
    def test_flat_object_with_schema_single_row(self, json_repo, tmp_path):
        p = tmp_path / "CoreSettings.json"
        p.write_text(
            json.dumps(
                {
                    "m_Version": 9,
                    "ServerUpdateRateLimit": 0.5,
                    "Enabled": True,
                    "DisplayName": "Expansion",
                    "ExtraKey": "extra",
                }
            ),
            encoding="utf-8",
        )
        defs, rows = json_repo.parse_file(str(p), _defs())

        assert len(rows) == 1
        keys = [fd.key for fd in defs]
        assert keys[0] == "m_Version"
        assert keys[1] == "ServerUpdateRateLimit"
        assert keys[2] == "Enabled"
        assert keys[3] == "DisplayName"
        assert "ExtraKey" in keys

        row = rows[0]
        assert row.values["m_Version"] == "9"
        assert row.values["ServerUpdateRateLimit"] == "0.5"
        assert row.values["Enabled"] == "true"
        assert row.values["ExtraKey"] == "extra"

    def test_flat_schema_types_kept(self, json_repo, tmp_path):
        p = tmp_path / "a.json"
        p.write_text(
            json.dumps(
                {
                    "m_Version": 9,
                    "ServerUpdateRateLimit": 0.5,
                    "Enabled": True,
                    "DisplayName": "x",
                    "ExtraKey": "x",
                }
            ),
            encoding="utf-8",
        )
        defs, _ = json_repo.parse_file(str(p), _defs())

        by_key = {fd.key: fd for fd in defs}
        assert by_key["m_Version"].type == FieldType.INT
        assert by_key["ServerUpdateRateLimit"].type == FieldType.FLOAT
        assert by_key["Enabled"].type == FieldType.BOOL
        assert by_key["ExtraKey"].type == FieldType.TEXT

    def test_flat_schema_declared_keys_missing_in_doc_skipped(self, json_repo, tmp_path):
        p = tmp_path / "b.json"
        p.write_text(json.dumps({"m_Version": 3}), encoding="utf-8")
        defs, rows = json_repo.parse_file(str(p), _defs())

        keys = [fd.key for fd in defs]
        assert "m_Version" in keys
        assert "DisplayName" not in keys
        assert len(rows) == 1

    def test_flat_schema_nested_values_stringified(self, json_repo, tmp_path):
        p = tmp_path / "c.json"
        p.write_text(
            json.dumps({"m_Version": 1, "Mapping": {"x": 1}, "List": [1, 2]}),
            encoding="utf-8",
        )
        defs, rows = json_repo.parse_file(str(p), _defs())

        keys = [fd.key for fd in defs]
        assert "Mapping" in keys
        assert "List" in keys
        row = rows[0]
        assert json.loads(row.values["Mapping"]) == {"x": 1}
        assert json.loads(row.values["List"]) == [1, 2]

    def test_array_of_objects_still_row_per_object_with_schema(self, json_repo, tmp_path):
        p = tmp_path / "items.json"
        p.write_text(json.dumps([{"id": 1}, {"id": 2}]), encoding="utf-8")
        defs, rows = json_repo.parse_file(str(p), _defs())

        assert len(rows) == 2
        assert [fd.key for fd in defs] == ["id"]

    def test_no_schema_backward_compatible(self, json_repo, tmp_path):
        p = tmp_path / "d.json"
        p.write_text(json.dumps({"a": 1, "b": "x"}), encoding="utf-8")
        defs, rows = json_repo.parse_file(str(p))

        assert [fd.key for fd in defs] == ["path", "value"]
        assert len(rows) == 2


class TestFlatSchemaSave:
    def test_save_coerces_declared_types(self, json_repo, tmp_path):
        p = tmp_path / "cfg.json"
        p.write_text(
            json.dumps(
                {"m_Version": 9, "ServerUpdateRateLimit": 0.5, "ExtraKey": "e"}
            ),
            encoding="utf-8",
        )
        defs, rows = json_repo.parse_file(str(p), _defs())

        by_key = {fd.key: fd for fd in defs}
        rows[0].values["m_Version"] = "12"
        rows[0].values["ServerUpdateRateLimit"] = "1.25"
        rows[0].values["ExtraKey"] = "changed"
        json_repo.save(str(p), rows)

        with open(p, encoding="utf-8") as fh:
            data = json.load(fh)
        assert data["m_Version"] == 12
        assert data["ServerUpdateRateLimit"] == 1.25
        assert data["ExtraKey"] == "changed"

    def test_save_coerces_bool(self, json_repo, tmp_path):
        p = tmp_path / "e.json"
        p.write_text(json.dumps({"Enabled": False}), encoding="utf-8")
        defs, rows = json_repo.parse_file(str(p), _defs())

        rows[0].values["Enabled"] = "true"
        json_repo.save(str(p), rows)

        with open(p, encoding="utf-8") as fh:
            data = json.load(fh)
        assert data["Enabled"] is True

    def test_save_preserves_nested_undeclared(self, json_repo, tmp_path):
        p = tmp_path / "f.json"
        p.write_text(
            json.dumps({"m_Version": 1, "Mapping": {"a": 1}}), encoding="utf-8"
        )
        defs, rows = json_repo.parse_file(str(p), _defs())

        rows[0].values["m_Version"] = "5"
        json_repo.save(str(p), rows)

        with open(p, encoding="utf-8") as fh:
            data = json.load(fh)
        assert data["m_Version"] == 5
        assert data["Mapping"] == {"a": 1}

    def test_save_flat_empty_rows(self, json_repo, tmp_path):
        p = tmp_path / "g.json"
        p.write_text(json.dumps({"m_Version": 1}), encoding="utf-8")
        json_repo.parse_file(str(p), _defs())
        json_repo.save(str(p), [])

        with open(p, encoding="utf-8") as fh:
            data = json.load(fh)
        assert data == {}


class TestXmlFlatSchema:
    def test_xml_parse_ignores_schema(self, tmp_path):
        p = tmp_path / "cfg.xml"
        p.write_text(
            '<root><option name="a" value="1"/></root>', encoding="utf-8"
        )
        defs, rows = XmlSettingsRepository().parse_file(str(p), _defs())

        keys = [fd.key for fd in defs]
        assert keys == ["option"]
        assert len(rows) == 1
        assert all(fd.type == FieldType.TEXT for fd in defs)
