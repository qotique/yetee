"""Acceptance tests for FileDisplay."""

from __future__ import annotations

from lxml import etree as ET

from controllers.table_controller import _collect_flag_names
from ui.file_display import FileDisplay
from repository.xml_utils import elem_text


# ── Parsing ─────────────────────────────────────────────────────────────


def test_load_file_parses_correct_row_count(small_types_file, mock_page):
    fd = FileDisplay(page=mock_page)
    fd.load_file(str(small_types_file))
    assert len(fd._rows) == 3


def test_load_file_parses_name(small_types_file, mock_page):
    fd = FileDisplay(page=mock_page)
    fd.load_file(str(small_types_file))
    assert fd._rows[0].values["name"] == "Item_Weapon_Knife"
    assert fd._rows[1].values["name"] == "Item_Weapon_Gun"
    assert fd._rows[2].values["name"] == "Food_Can"


def test_load_file_parses_numeric_fields(small_types_file, mock_page):
    fd = FileDisplay(page=mock_page)
    fd.load_file(str(small_types_file))
    assert fd._rows[0].values["nominal"] == "10"
    assert fd._rows[0].values["lifetime"] == "14400"
    assert fd._rows[0].values["restock"] == "1800"
    assert fd._rows[0].values["min"] == "6"
    assert fd._rows[0].values["quantmin"] == "-1"
    assert fd._rows[0].values["quantmax"] == "-1"
    assert fd._rows[0].values["cost"] == "100"


def test_load_file_parses_category(small_types_file, mock_page):
    fd = FileDisplay(page=mock_page)
    fd.load_file(str(small_types_file))
    assert fd._rows[0].values["category"] == "weapons"
    assert fd._rows[2].values["category"] == "food"


def test_load_file_parses_usage(small_types_file, mock_page):
    fd = FileDisplay(page=mock_page)
    fd.load_file(str(small_types_file))
    assert "Military" in fd._rows[0].values["usage"]
    assert "Police" in fd._rows[0].values["usage"]
    assert fd._rows[2].values["usage"] == "Town, Village"


def test_load_file_parses_value(small_types_file, mock_page):
    fd = FileDisplay(page=mock_page)
    fd.load_file(str(small_types_file))
    assert fd._rows[0].values["value"] == "Tier3"
    assert fd._rows[2].values["value"] == "Tier1"


def test_load_file_parses_flags(small_types_file, mock_page):
    fd = FileDisplay(page=mock_page)
    fd.load_file(str(small_types_file))
    assert fd._rows[0].flags["count_in_cargo"] == "0"
    assert fd._rows[0].flags["count_in_map"] == "1"
    assert fd._rows[2].flags["count_in_player"] == "1"


# ── Filter ──────────────────────────────────────────────────────────────


def test_apply_filter_by_name(small_types_file, mock_page):
    fd = FileDisplay(page=mock_page)
    fd.load_file(str(small_types_file))
    fd._apply_filter("knife")
    assert len(fd._filtered) == 1
    assert fd._filtered[0] == 0


def test_apply_filter_or(small_types_file, mock_page):
    fd = FileDisplay(page=mock_page)
    fd.load_file(str(small_types_file))
    fd._apply_filter("knife|gun")
    assert len(fd._filtered) == 2


def test_apply_filter_empty_returns_all(small_types_file, mock_page):
    fd = FileDisplay(page=mock_page)
    fd.load_file(str(small_types_file))
    fd._apply_filter("")
    assert len(fd._filtered) == 3


def test_apply_filter_no_match(small_types_file, mock_page):
    fd = FileDisplay(page=mock_page)
    fd.load_file(str(small_types_file))
    fd._apply_filter("zzzznotfound")
    assert len(fd._filtered) == 0


# ── Caching ─────────────────────────────────────────────────────────────


def test_cache_hit_on_reload(small_types_file, mock_page):
    fd = FileDisplay(page=mock_page)
    fd.load_file(str(small_types_file))
    cache_key = str(small_types_file)
    rows = fd.cache.get_rows(cache_key)
    assert rows is not None
    assert len(rows) == 3


# ── Clear ───────────────────────────────────────────────────────────────


def test_clear_resets_state(small_types_file, mock_page):
    fd = FileDisplay(page=mock_page)
    fd.load_file(str(small_types_file))
    fd.clear()
    assert fd._path is None
    assert fd._rows == []
    assert fd._filtered == []
    assert fd._dirty is False
    assert fd.control.visible is False


# ── Pagination ──────────────────────────────────────────────────────────


def test_pagination_initial_page(large_types_file, mock_page):
    fd = FileDisplay(page=mock_page)
    fd.load_file(str(large_types_file))
    assert fd._page_idx == 0


def test_pagination_next(large_types_file, mock_page):
    fd = FileDisplay(page=mock_page)
    fd.load_file(str(large_types_file))
    fd._next_page(None)
    assert fd._page_idx == 1


def test_pagination_prev(large_types_file, mock_page):
    fd = FileDisplay(page=mock_page)
    fd.load_file(str(large_types_file))
    fd._next_page(None)
    fd._prev_page(None)
    assert fd._page_idx == 0


def test_pagination_stays_in_bounds(large_types_file, mock_page):
    fd = FileDisplay(page=mock_page)
    fd.load_file(str(large_types_file))
    # Try to go before page 0
    fd._prev_page(None)
    assert fd._page_idx == 0


# ── Dirty flag ──────────────────────────────────────────────────────────


def test_edit_sets_dirty(small_types_file, mock_page):
    fd = FileDisplay(page=mock_page)
    fd.load_file(str(small_types_file))
    fd._dirty = False
    fd._on_field_change(None)
    assert fd._dirty is True


# ── Save ────────────────────────────────────────────────────────────────


def test_save_updates_xml(small_types_file, mock_page):
    fd = FileDisplay(page=mock_page)
    fd.load_file(str(small_types_file))
    # Modify nominal via widget
    fd._pool_fields[0][1].value = "99"
    fd._on_field_change(None)
    fd.save_current(None)
    # Re-read and verify
    tree = ET.parse(str(small_types_file))
    root = tree.getroot()
    types = root.findall("type")
    assert types[0].find("nominal").text == "99"
    # Other rows unchanged
    assert types[1].find("nominal").text == "5"


def test_save_preserves_unchanged_rows(small_types_file, mock_page):
    fd = FileDisplay(page=mock_page)
    fd.load_file(str(small_types_file))
    fd.save_current(None)
    tree = ET.parse(str(small_types_file))
    root = tree.getroot()
    types = root.findall("type")
    assert len(types) == 3


# ── Multi-select ────────────────────────────────────────────────────────


def test_multi_select_toggle(mock_page, small_types_file):
    fd = FileDisplay(page=mock_page)
    fd.load_file(str(small_types_file))
    assert fd._multi_select_mode is False
    fd._toggle_multi_select(None)
    assert fd._multi_select_mode is True
    fd._toggle_multi_select(None)
    assert fd._multi_select_mode is False


# ── Detail panel: usage chips ───────────────────────────────────────────


def test_detail_usage_add(small_types_file, mock_page):
    fd = FileDisplay(page=mock_page)
    fd.load_file(str(small_types_file))
    fd._on_row_click(0)
    fd._on_detail_usage_add("Industrial")
    assert "Industrial" in fd._detail_usage_set


def test_detail_usage_remove(small_types_file, mock_page):
    fd = FileDisplay(page=mock_page)
    fd.load_file(str(small_types_file))
    fd._on_row_click(0)
    fd._on_detail_usage_add("Military")
    fd._detail_remove_usage("Military")
    assert "Military" not in fd._detail_usage_set


def test_detail_value_add(small_types_file, mock_page):
    fd = FileDisplay(page=mock_page)
    fd.load_file(str(small_types_file))
    fd._on_row_click(0)
    fd._on_detail_value_add("Tier1")
    assert "Tier1" in fd._detail_value_set


def test_detail_value_remove(small_types_file, mock_page):
    fd = FileDisplay(page=mock_page)
    fd.load_file(str(small_types_file))
    fd._on_row_click(0)
    fd._on_detail_value_add("Tier3")
    fd._detail_remove_value("Tier3")
    assert "Tier3" not in fd._detail_value_set


# ── Batch editing ───────────────────────────────────────────────────────


def test_batch_save_field(small_types_file, mock_page):
    fd = FileDisplay(page=mock_page)
    fd.load_file(str(small_types_file))
    # Select two rows
    fd._on_row_click(0)
    fd._multi_select_mode = True
    fd._on_row_click(1)
    assert len(fd._selected_row_indices) == 2
    # Apply batch edit — nominal
    tf = fd._batch_fields.get("nominal")
    assert tf is not None, "batch field 'nominal' not found"
    tf.value = "77"
    fd._batch_save_field("nominal")
    assert fd._rows[0].values["nominal"] == "77"
    assert fd._rows[1].values["nominal"] == "77"


# ── Standalone helpers ──────────────────────────────────────────────────


def testelem_text_missing(small_types_file):
    tree = ET.parse(str(small_types_file))
    root = tree.getroot()
    typ = root.findall("type")[0]
    assert elem_text(typ, "nonexistent") == ""


def testelem_text_present(small_types_file):
    tree = ET.parse(str(small_types_file))
    root = tree.getroot()
    typ = root.findall("type")[0]
    assert elem_text(typ, "nominal") == "10"


def test_collect_flag_names(small_types_file, mock_page):
    fd = FileDisplay(page=mock_page)
    fd.load_file(str(small_types_file))
    names = _collect_flag_names(fd._rows)
    assert "count_in_cargo" in names
    assert "count_in_map" in names
    assert "count_in_player" in names


# ── Text files (json / txt) ─────────────────────────────────────────────


def test_load_json_file_uses_text_mode(mock_page, tmp_path):
    path = tmp_path / "config.json"
    path.write_text('{"a": 1}', encoding="utf-8")
    fd = FileDisplay(page=mock_page)
    fd.load_file(str(path))
    assert fd._text_mode is True
    assert fd._text_editor.value == '{"a": 1}'
    assert fd._path == str(path)


def test_load_txt_file_uses_text_mode(mock_page, tmp_path):
    import asyncio

    path = tmp_path / "readme.txt"
    path.write_text("hello\nworld", encoding="utf-8")
    fd = FileDisplay(page=mock_page)
    asyncio.run(fd.load_file_async(str(path)))
    assert fd._text_mode is True
    assert fd._text_editor.value == "hello\nworld"


def test_load_xml_kd_file_uses_table_mode(small_types_file, mock_page):
    fd = FileDisplay(page=mock_page)
    fd.load_file(str(small_types_file))
    assert fd._text_mode is False
    assert len(fd._rows) == 3


def test_save_text_file_writes_content(mock_page, tmp_path):
    path = tmp_path / "config.json"
    path.write_text("{}", encoding="utf-8")
    fd = FileDisplay(page=mock_page)
    fd.load_file(str(path))
    fd._text_editor.value = '{"new": true}'
    fd.save_current(None)
    assert path.read_text(encoding="utf-8") == '{"new": true}'


def test_save_text_file_single_file_flush(mock_page, tmp_path):
    path = tmp_path / "notes.txt"
    path.write_text("v1", encoding="utf-8")
    fd = FileDisplay(page=mock_page)
    fd.load_file(str(path))
    fd._text_editor.value = "v2"
    fd.save_file()
    assert path.read_text(encoding="utf-8") == "v2"


def test_text_mode_reset_after_xml_load(small_types_file, mock_page, tmp_path):
    txt = tmp_path / "a.txt"
    txt.write_text("x", encoding="utf-8")
    fd = FileDisplay(page=mock_page)
    fd.load_file(str(txt))
    assert fd._text_mode is True
    fd.load_file(str(small_types_file))
    assert fd._text_mode is False
    assert len(fd._rows) == 3


# ── Undo / redo availability ───────────────────────────────────────────


def test_undo_disabled_after_load_without_edits(small_types_file, mock_page):
    fd = FileDisplay(page=mock_page)
    fd.load_file(str(small_types_file))
    assert not fd.can_undo
    assert fd._undo_btn.disabled
    assert not fd.can_redo
    assert fd._redo_btn.disabled


def test_first_edit_enables_undo(small_types_file, mock_page):
    fd = FileDisplay(page=mock_page)
    fd.load_file(str(small_types_file))
    fd._on_field_change(None)
    assert fd.can_undo
    assert not fd._undo_btn.disabled


def test_first_edit_undo_restores_original(small_types_file, mock_page):
    fd = FileDisplay(page=mock_page)
    fd.load_file(str(small_types_file))
    fd._on_field_change(None)
    original = dict(fd._session.rows[0].values)
    fd._session.rows[0].values["nominal"] = "999"
    assert fd._session.undo() is True
    assert fd._session.rows[0].values == original
