"""Tests for SearchController's case-insensitive search option."""

from __future__ import annotations

from controllers.search_controller import (
    EMPTY_CATEGORY_MARKER,
    SearchController,
)
from models.row_data import RowData


def _row(name: str) -> RowData:
    return RowData(values={"name": name}, flags={})


def test_search_is_case_insensitive_by_default():
    ctrl = SearchController()
    ctrl.set_search("knife")
    rows = [_row("Item_Weapon_Knife"), _row("Food_Can")]
    assert ctrl.filter_rows(rows) == [0]


def test_case_sensitive_search_requires_exact_case():
    ctrl = SearchController()
    ctrl.set_search("knife", case_sensitive=True)
    rows = [_row("Item_Weapon_Knife"), _row("Food_Can")]
    assert ctrl.filter_rows(rows) == []


def test_case_sensitive_search_matches_exact_case():
    ctrl = SearchController()
    ctrl.set_search("Knife", case_sensitive=True)
    rows = [_row("Item_Weapon_Knife"), _row("Item_Weapon_knife")]
    assert ctrl.filter_rows(rows) == [0]


def test_case_sensitive_flag_reflected_in_property():
    ctrl = SearchController()
    assert ctrl.case_sensitive is False
    ctrl.set_search("knife", case_sensitive=True)
    assert ctrl.case_sensitive is True


def _full_row(name: str, category: str = "food") -> RowData:
    return RowData(
        values={"name": name, "category": category, "usage": "", "value": ""},
        flags={},
    )


def test_set_filters_matches_category():
    ctrl = SearchController()
    ctrl.set_filters({"category": "weapons"})
    rows = [
        _full_row("Item_A", "food"),
        _full_row("Item_B", "weapons"),
        _full_row("Item_C", "weapons"),
    ]
    assert ctrl.filter_rows(rows) == [1, 2]


def test_set_filters_is_case_insensitive():
    ctrl = SearchController()
    ctrl.set_filters({"category": "WEAPONS"})
    rows = [_full_row("Item_A", "food"), _full_row("Item_B", "weapons")]
    assert ctrl.filter_rows(rows) == [1]


def test_set_filters_multiple_values_or():
    ctrl = SearchController()
    ctrl.set_filters({"category": "food|weapons"})
    rows = [_full_row("A", "food"), _full_row("B", "tools"), _full_row("C", "weapons")]
    assert ctrl.filter_rows(rows) == [0, 2]


def test_empty_marker_matches_empty_column():
    ctrl = SearchController()
    ctrl.set_filters({"category": EMPTY_CATEGORY_MARKER})
    rows = [
        _full_row("A", "food"),
        RowData(values={"name": "B", "category": "", "usage": "", "value": ""}, flags={}),
    ]
    assert ctrl.filter_rows(rows) == [1]


def test_set_filters_replaces_previous():
    ctrl = SearchController()
    ctrl.set_filters({"category": "food"})
    ctrl.set_filters({"value": "Tier1"})
    assert ctrl.filters == {"value": "tier1"}


def test_set_filters_empty_value_ignored():
    ctrl = SearchController()
    ctrl.set_filters({"category": ""})
    rows = [_full_row("A", "food"), _full_row("B", "weapons")]
    assert ctrl.filter_rows(rows) == [0, 1]


def test_reset_clears_filters():
    ctrl = SearchController()
    ctrl.set_filters({"category": "food"})
    ctrl.reset()
    assert ctrl.filters == {}
    rows = [_full_row("A", "food"), _full_row("B", "weapons")]
    assert ctrl.filter_rows(rows) == [0, 1]
