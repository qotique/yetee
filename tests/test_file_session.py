"""Unit tests for the flet-free FileSession controller."""

from __future__ import annotations

from unittest.mock import AsyncMock, Mock

from lxml import etree as ET

from controllers.commands import LIFETIME_OPTIONS
from controllers.file_session import FileSession
from models.row_data import RowData
from core.protocols import IXmlRepository
from repository.file_cache import FileCache


def _row(name: str = "Item_A", category: str = "food", elem=None) -> RowData:
    return RowData(
        values={
            "name": name,
            "nominal": "10",
            "lifetime": "3600",
            "restock": "300",
            "min": "5",
            "quantmin": "-1",
            "quantmax": "10",
            "cost": "-1",
            "category": category,
            "usage": "Town",
            "value": "Tier1",
        },
        flags={"count_in_cargo": "0", "count_in_map": "1"},
        elem=elem,
    )


def _make_session(repo=None, cache=None, path="/tmp/types.xml"):
    repo = repo or Mock(spec=IXmlRepository)
    cache = cache or FileCache()
    session = FileSession(repo, cache)
    if path is not None:
        session.load_setup(path)
    return session


def _cached_tree(cache, path, row_count=2):
    root = ET.Element("types")
    elems = []
    for i in range(row_count):
        elem = ET.SubElement(root, "type")
        elem.set("name", f"Item_{i}")
        elems.append(elem)
    cache.set_tree(path, ET.ElementTree(root))
    return elems


def test_load_setup_resets_state():
    session = _make_session()
    session.rows = [_row()]
    session.selected_row_indices = {0}
    session.mark_dirty()
    session.load_setup("/tmp/new.xml")
    assert session.path == "/tmp/new.xml"
    assert session.rows == []
    assert session.filtered == []
    assert session.selected_row_idx is None
    assert not session.selected_row_indices
    assert not session.dirty
    assert not session.can_undo


def test_clear_all_resets_path():
    session = _make_session()
    session.mark_dirty()
    session.clear_all()
    assert session.path is None
    assert not session.dirty


def test_apply_filter_matches_query_and_filters():
    session = _make_session()
    session.rows = [
        _row("Item_Weapon_Knife", "weapons"),
        _row("Item_Weapon_Gun", "weapons"),
        _row("Food_Can", "food"),
    ]
    session.apply_filter("knife", False, {"category": "weapons"})
    assert session.filtered == [0]


def test_apply_filter_category_only():
    session = _make_session()
    session.rows = [_row("A", "food"), _row("B", "weapons")]
    session.apply_filter("", False, {"category": "weapons"})
    assert session.filtered == [1]


def test_add_type_inserts_row_and_tree_elem():
    cache = FileCache()
    elems = _cached_tree(cache, "/tmp/types.xml", row_count=1)
    session = _make_session(cache=cache)
    session.rows = [_row("Item_0", elem=elems[0])]
    assert session.add_type() is True
    assert len(session.rows) == 2
    assert session.rows[0].values["name"] == ""
    assert session.rows[0].flags["count_in_cargo"] == "0"
    root = cache.get_tree("/tmp/types.xml").getroot()
    assert len(root.findall("type")) == 2
    assert session.dirty
    assert session.can_undo


def test_add_type_returns_false_without_path():
    session = _make_session(path=None)
    assert session.add_type() is False


def test_delete_selected_removes_rows_and_elems():
    cache = FileCache()
    elems = _cached_tree(cache, "/tmp/types.xml", row_count=2)
    session = _make_session(cache=cache)
    session.rows = [_row("Item_0", elem=elems[0]), _row("Item_1", elem=elems[1])]
    session.selected_row_indices = {0}
    assert session.delete_selected() is True
    assert len(session.rows) == 1
    assert session.rows[0].values["name"] == "Item_1"
    root = cache.get_tree("/tmp/types.xml").getroot()
    assert len(root.findall("type")) == 1
    assert not session.selected_row_indices


def test_delete_selected_returns_false_when_none_selected():
    session = _make_session()
    assert session.delete_selected() is False


def test_randomize_updates_only_target_rows():
    session = _make_session()
    session.rows = [_row("A", "food"), _row("B", "food")]
    session.randomize({0})
    assert session.rows[0].values["nominal"] != "10"
    assert session.rows[1].values["nominal"] == "10"
    assert session.rows[0].values["lifetime"] in [
        str(v) for v in LIFETIME_OPTIONS
    ]
    assert session.dirty


def test_batch_apply_field_writes_selected_rows():
    session = _make_session()
    session.rows = [_row("A"), _row("B"), _row("C")]
    session.selected_row_indices = {0, 2}
    session.batch_apply_field("nominal", "99")
    assert session.rows[0].values["nominal"] == "99"
    assert session.rows[1].values["nominal"] == "10"
    assert session.rows[2].values["nominal"] == "99"
    assert session.dirty


def test_batch_apply_chipset_writes_selected_rows():
    session = _make_session()
    session.rows = [_row("A"), _row("B")]
    session.selected_row_indices = {0, 1}
    session.batch_apply_chipset("usage", "Military, Police")
    assert session.rows[0].values["usage"] == "Military, Police"
    assert session.rows[1].values["usage"] == "Military, Police"


def test_batch_apply_flag_writes_selected_rows():
    session = _make_session()
    session.rows = [_row("A"), _row("B")]
    session.selected_row_indices = {0, 1}
    session.batch_apply_flag("count_in_map", "0")
    assert session.rows[0].flags["count_in_map"] == "0"
    assert session.rows[1].flags["count_in_map"] == "0"


def test_undo_restores_row_values():
    session = _make_session()
    session.rows = [_row("A")]
    session.record_undo()
    session.rows[0].values["nominal"] = "99"
    assert session.undo() is True
    assert session.rows[0].values["nominal"] == "10"
    assert session.redo() is True
    assert session.rows[0].values["nominal"] == "99"


def test_save_calls_repository():
    repo = Mock(spec=IXmlRepository)
    session = _make_session(repo=repo)
    session.rows = [_row()]
    session.save()
    repo.save.assert_called_once_with("/tmp/types.xml", session.rows)


async def test_save_async_awaits_repository():
    repo = Mock(spec=IXmlRepository)
    repo.save_async = AsyncMock()
    session = _make_session(repo=repo)
    session.rows = [_row()]
    await session.save_async()
    repo.save_async.assert_awaited_once_with("/tmp/types.xml", session.rows)


def test_save_without_path_is_noop():
    repo = Mock(spec=IXmlRepository)
    session = _make_session(repo=repo, path=None)
    session.save()
    repo.save.assert_not_called()


def test_pagination_navigation():
    session = _make_session()
    session.rows = [_row(f"Item_{i}") for i in range(55)]
    session.filtered = list(range(55))
    assert session.total_pages() == 2
    session.next_page()
    assert session.page_index == 1
    session.prev_page()
    assert session.page_index == 0


def test_refilter_uses_current_filters():
    session = _make_session()
    session.rows = [_row("A", "food"), _row("B", "weapons")]
    session.apply_filter("", False, {"category": "weapons"})
    session.rows.append(_row("C", "weapons"))
    session.refilter()
    assert session.filtered == [1, 2]