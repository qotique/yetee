from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from repository.settings_repository import JsonSettingsRepository, XmlSettingsRepository
from ui.settings_table_display import SettingsTableDisplay


@pytest.fixture
def page():
    page = MagicMock()
    page.theme = None
    page.dark_theme = None
    page.on_keyboard_event = None
    return page


@pytest.fixture
def display(page) -> SettingsTableDisplay:
    return SettingsTableDisplay(
        page=page,
        xml_repo=XmlSettingsRepository(),
        json_repo=JsonSettingsRepository(),
    )


def test_initial_state_hidden(display):
    assert display.control.visible is False
    assert display.is_dirty is False
    assert display._path is None


def test_load_json_table_file(display, tmp_path):
    p = tmp_path / "cfg.json"
    p.write_text('{"a": 1, "b": "x"}', encoding="utf-8")
    display.set_entity("MOD")
    display.load_file(str(p))
    assert display._renderer == "json"
    assert len(display._rows) == 2
    assert [fd.key for fd in display._field_defs] == ["path", "value"]
    assert display.control.visible is True


def test_load_xml_table_file(display, tmp_path):
    p = tmp_path / "cfg.xml"
    p.write_text(
        '<root><option name="a" value="1"/><option name="b" value="2"/></root>',
        encoding="utf-8",
    )
    display.set_entity("MOD")
    display.load_file(str(p))

    assert display._renderer == "xml"
    assert len(display._rows) == 2
    assert display.control.visible is True


def test_load_txt_file_uses_text_editor(display, tmp_path):
    p = tmp_path / "notes.txt"
    p.write_text("line one\nline two", encoding="utf-8")
    display.set_entity("MOD")
    display.load_file(str(p))

    assert display._renderer == "txt"
    assert display._text_container.visible is True
    assert display._text_editor.value == "line one\nline two"


def test_save_txt_file_triggers_on_saved(display, tmp_path):
    p = tmp_path / "notes.txt"
    p.write_text("hi", encoding="utf-8")
    saved = []
    display.on_saved = lambda: saved.append(True)
    display.set_entity("MOD")
    display.load_file(str(p))

    display._text_editor.value = "changed"
    display.save_current()

    assert p.read_text() == "changed"
    assert saved == [True]
    assert not display.is_dirty


def test_save_xml_writes_back(display, tmp_path):
    p = tmp_path / "cfg.xml"
    p.write_text(
        '<root><option name="a" value="1"/><option name="b" value="2"/></root>',
        encoding="utf-8",
    )
    saved = []
    display.on_saved = lambda: saved.append(True)
    display.set_entity("MOD")
    display.load_file(str(p))

    col = [fd.key for fd in display._field_defs].index("value")
    display._table_ctrl._pool_fields[0][col].value = "77"
    display.save_current()

    text = p.read_text(encoding="utf-8")
    assert 'value="77"' in text
    assert saved == [True]


def test_save_json_roundtrip(display, tmp_path):
    p = tmp_path / "cfg.json"
    p.write_text('{"a": 1, "b": true}', encoding="utf-8")
    display.on_saved = lambda: None
    display.set_entity("MOD")
    display.load_file(str(p))

    rows = display._rows
    col = [fd.key for fd in display._field_defs].index("value")
    display._table_ctrl._pool_fields[0][col].value = "9"
    display.save_current()

    import json

    assert json.loads(p.read_text()) == {"a": 9, "b": True}


def test_clear_resets_state(display, tmp_path):
    p = tmp_path / "cfg.json"
    p.write_text('{"a": 1}', encoding="utf-8")
    display.set_entity("MOD")
    display.load_file(str(p))
    display.clear()

    assert display._path is None
    assert display.control.visible is False
    assert display._rows == []
    assert not display.is_dirty


def test_clear_cache(display, tmp_path):
    p = tmp_path / "cfg.json"
    p.write_text('{"a": 1}', encoding="utf-8")
    display.set_entity("MOD")
    display.load_file(str(p))
    display.clear_cache(str(p))

    assert str(p) not in display._json_repo._docs


def test_load_file_async_json(page, tmp_path):
    display = SettingsTableDisplay(
        page=page,
        xml_repo=XmlSettingsRepository(),
        json_repo=JsonSettingsRepository(),
    )
    p = tmp_path / "cfg.json"
    p.write_text('{"a": 1}', encoding="utf-8")
    display.set_entity("MOD")

    import asyncio

    asyncio.run(display.load_file_async(str(p)))

    assert display._renderer == "json"
    assert len(display._rows) == 1


class JsonDisplayAlias:
    pass


def test_parse_table_file_caches_result(display, tmp_path):
    p = tmp_path / "cfg.json"
    p.write_text('{"a": 1}', encoding="utf-8")
    display.set_entity("MOD")
    result = display._parse_table_file(str(p), "json")
    assert str(p) in display._parsed_cache
    assert display._parse_table_file(str(p), "json") is result


def test_clear_resets_parsed_cache(display, tmp_path):
    p = tmp_path / "cfg.json"
    p.write_text('{"a": 1}', encoding="utf-8")
    display.set_entity("MOD")
    display._parse_table_file(str(p), "json")
    assert str(p) in display._parsed_cache
    display.clear()
    assert display._parsed_cache == {}


def test_clear_cache_evicts_parsed(display, tmp_path):
    p = tmp_path / "cfg.json"
    p.write_text('{"a": 1}', encoding="utf-8")
    display.set_entity("MOD")
    display._parse_table_file(str(p), "json")
    display.clear_cache(str(p))
    assert str(p) not in display._parsed_cache


def test_preload_cached_populates_cache_with_progress(display, tmp_path):
    p1 = tmp_path / "a.json"
    p2 = tmp_path / "b.json"
    p1.write_text('{"x": 1}', encoding="utf-8")
    p2.write_text('{"y": 2}', encoding="utf-8")
    display.set_entity("MOD")

    import asyncio

    reported: list[tuple[int, int]] = []
    progress = lambda done, total: reported.append((done, total))
    asyncio.run(display.preload_cached([str(p1), str(p2)], on_progress=progress))

    assert reported == [(1, 2), (2, 2)]
    assert str(p1) in display._parsed_cache
    assert str(p2) in display._parsed_cache


def test_preload_cached_skips_txt_and_cached(display, tmp_path):
    t = tmp_path / "notes.txt"
    t.write_text("plain", encoding="utf-8")
    j = tmp_path / "cfg.json"
    j.write_text('{"a": 1}', encoding="utf-8")
    display.set_entity("MOD")
    display._parse_table_file(str(j), "json")

    import asyncio

    asyncio.run(display.preload_cached([str(t), str(j)]))

    assert str(t) not in display._parsed_cache


def test_preload_cached_cancel_check_stops(display, tmp_path):
    p1 = tmp_path / "a.json"
    p2 = tmp_path / "b.json"
    p1.write_text('{"x": 1}', encoding="utf-8")
    p2.write_text('{"y": 2}', encoding="utf-8")
    display.set_entity("MOD")

    import asyncio

    counted = []

    def cancel_check():
        return len(counted) >= 1

    def on_progress(done, total):
        counted.append((done, total))

    asyncio.run(
        display.preload_cached(
            [str(p1), str(p2)], on_progress=on_progress, cancel_check=cancel_check
        )
    )

    assert counted == [(1, 2)]


def test_preload_cached_skips_malformed_files(display, tmp_path):
    p1 = tmp_path / "good.json"
    p2 = tmp_path / "broken.json"
    p3 = tmp_path / "broken.xml"
    p1.write_text('{"x": 1}', encoding="utf-8")
    p2.write_text("not json", encoding="utf-8")
    p3.write_text("<unclosed>", encoding="utf-8")
    display.set_entity("MOD")

    import asyncio

    reported: list[tuple[int, int]] = []
    progress = lambda done, total: reported.append((done, total))
    asyncio.run(
        display.preload_cached([str(p1), str(p2), str(p3)], on_progress=progress)
    )

    assert reported == [(1, 3), (2, 3), (3, 3)]
    assert str(p1) in display._parsed_cache
    assert str(p2) not in display._parsed_cache
    assert str(p3) not in display._parsed_cache


def test_preload_cached_bad_file_does_not_abort_later_files(display, tmp_path):
    p1 = tmp_path / "broken.json"
    p2 = tmp_path / "good.json"
    p1.write_text("!!!", encoding="utf-8")
    p2.write_text('{"ok": true}', encoding="utf-8")
    display.set_entity("MOD")

    import asyncio

    asyncio.run(display.preload_cached([str(p1), str(p2)]))
    assert str(p1) not in display._parsed_cache
    assert str(p2) in display._parsed_cache
