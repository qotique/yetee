from __future__ import annotations

import json

import pytest

from exceptions import AccessError, ParseError
from models.field_def import FieldType
from repository.settings_repository import (
    JsonSettingsRepository,
    XmlSettingsRepository,
)


@pytest.fixture
def xml_path(tmp_path):
    p = tmp_path / "mod_config.xml"
    p.write_text(
        """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<modsettings>
  <option name="enabled" value="1"/>
  <option name="frequency" value="30"/>
  <option name="label" value="hello"/>
  <option name="enabled" value="0"/>
</modsettings>
""",
        encoding="utf-8",
    )
    return str(p)


@pytest.fixture
def flat_xml_path(tmp_path):
    p = tmp_path / "flat.xml"
    p.write_text(
        """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<settings>
  <name>MyServer</name>
  <max_players>64</max_players>
</settings>
""",
        encoding="utf-8",
    )
    return str(p)


class TestXmlSettingsRepository:
    def test_parse_repeated_children_as_records(self, xml_path):
        defs, rows = XmlSettingsRepository().parse_file(xml_path)
        assert len(rows) == 4
        assert [fd.key for fd in defs] == ["name", "value"]
        assert rows[0].values["name"] == "enabled"
        assert rows[0].values["value"] == "1"
        assert rows[1].values["value"] == "30"

    def test_parse_flat_xml_single_row(self, flat_xml_path):
        defs, rows = XmlSettingsRepository().parse_file(flat_xml_path)
        assert rows[0].values["name"] == "MyServer"
        assert rows[0].values["max_players"] == "64"
        assert [fd.label for fd in defs] == ["max_players", "name"]

    def test_save_writes_back_values(self, xml_path):
        repo = XmlSettingsRepository()
        defs, rows = repo.parse_file(xml_path)
        rows[0].values["value"] = "5"
        repo.save(xml_path, rows)

        repo2 = XmlSettingsRepository()
        _, rows2 = repo2.parse_file(xml_path)
        assert rows2[0].values["value"] == "5"
        assert rows2[1].values["value"] == "30"

    def test_save_without_parse_raises(self, tmp_path):
        p = tmp_path / "x.xml"
        p.write_text("<root/>", encoding="utf-8")
        with pytest.raises(ParseError):
            XmlSettingsRepository().save(str(p), [])

    def test_parse_missing_file_raises_access(self, tmp_path):
        with pytest.raises(AccessError):
            XmlSettingsRepository().parse_file(str(tmp_path / "missing.xml"))

    def test_parse_invalid_xml_raises_parse(self, tmp_path):
        p = tmp_path / "bad.xml"
        p.write_text("<root><unclosed></root>", encoding="utf-8")
        with pytest.raises(ParseError):
            XmlSettingsRepository().parse_file(str(p))

    def test_parse_ignores_comments_and_pi(self, tmp_path):
        p = tmp_path / "commented.xml"
        p.write_text(
            "<root>"
            "<!-- a comment -->"
            "<?processing data?>"
            "<item name=\"a\">1</item>"
            "<item name=\"b\">2</item>"
            "</root>",
            encoding="utf-8",
        )
        defs, rows = XmlSettingsRepository().parse_file(str(p))
        assert [fd.key for fd in defs] == ["name"]
        assert len(rows) == 2

    def test_invalidate_cache(self, xml_path):
        repo = XmlSettingsRepository()
        repo.parse_file(xml_path)
        repo.invalidate_cache(xml_path)
        assert xml_path not in repo._trees


class TestJsonSettingsRepository:
    def test_object_of_scalars_flattened_to_path_value(self, tmp_path):
        p = tmp_path / "cfg.json"
        p.write_text(
            json.dumps({"server": {"name": "MyGreat", "port": 2400}, "debug": True}),
            encoding="utf-8",
        )
        defs, rows = JsonSettingsRepository().parse_file(str(p))
        assert [fd.key for fd in defs] == ["path", "value"]
        keys = {r.values["path"] for r in rows}
        assert keys == {"debug", "server.name", "server.port"}
        by_key = {r.values["path"]: r.values["value"] for r in rows}
        assert by_key["server.name"] == "MyGreat"
        assert by_key["server.port"] == "2400"
        assert by_key["debug"] == "true"

    def test_array_of_objects_row_per_object(self, tmp_path):
        p = tmp_path / "items.json"
        p.write_text(
            json.dumps([{"id": 1, "name": "a"}, {"id": 2, "name": "bb"}]),
            encoding="utf-8",
        )
        defs, rows = JsonSettingsRepository().parse_file(str(p))
        assert [fd.key for fd in defs] == ["id", "name"]
        assert len(rows) == 2
        assert rows[0].values["id"] == "1"
        assert rows[1].values["name"] == "bb"

    def test_save_object_roundtrip(self, tmp_path):
        p = tmp_path / "cfg.json"
        p.write_text(json.dumps({"enabled": True, "count": 5}), encoding="utf-8")
        repo = JsonSettingsRepository()
        defs, rows = repo.parse_file(str(p))
        rows[0].values["value"] = "false"
        rows[1].values["value"] = "12"
        repo.save(str(p), rows)

        with open(p, encoding="utf-8") as fh:
            data = json.load(fh)
        assert data == {"enabled": False, "count": 12}

    def test_save_array_roundtrip(self, tmp_path):
        p = tmp_path / "items.json"
        p.write_text(json.dumps([{"id": 1}, {"id": 2}]), encoding="utf-8")
        repo = JsonSettingsRepository()
        _, rows = repo.parse_file(str(p))
        rows[0].values["id"] = "9"
        repo.save(str(p), rows)

        with open(p, encoding="utf-8") as fh:
            data = json.load(fh)
        assert data == [{"id": 9}, {"id": 2}]

    def test_save_without_parse_raises(self, tmp_path):
        p = tmp_path / "n.json"
        p.write_text("{}", encoding="utf-8")
        with pytest.raises(ParseError):
            JsonSettingsRepository().save(str(p), [])

    def test_parse_invalid_json_raises(self, tmp_path):
        p = tmp_path / "bad.json"
        p.write_text("{not json", encoding="utf-8")
        with pytest.raises(ParseError):
            JsonSettingsRepository().parse_file(str(p))

    def test_parse_missing_file_raises_access(self, tmp_path):
        with pytest.raises(AccessError):
            JsonSettingsRepository().parse_file(str(tmp_path / "missing.json"))

    def test_field_def_types_are_text(self, tmp_path):
        p = tmp_path / "c.json"
        p.write_text(json.dumps({"a": 1}), encoding="utf-8")
        defs, _ = JsonSettingsRepository().parse_file(str(p))
        assert all(fd.type == FieldType.TEXT for fd in defs)