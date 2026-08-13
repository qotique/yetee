"""Tests for SearchController's case-insensitive search option."""

from __future__ import annotations

from controllers.search_controller import SearchController
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
