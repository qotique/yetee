"""Tests for the generic FilterMenu widget."""

from __future__ import annotations

from unittest.mock import Mock

import flet as ft

from ui.filter_menu import FilterMenu, FilterSpec


def _make_menu(is_cat=None):
    spec = FilterSpec(
        key="category",
        label="Category",
        options=["food", "weapons"],
        empty_marker="__empty__",
    )
    return FilterMenu(spec, on_changed=Mock(), is_cat=is_cat)


def test_filter_value_empty_initially():
    menu = _make_menu()
    assert menu.filter_value() == ""


def test_toggle_adds_and_removes_value():
    menu = _make_menu()
    menu._toggle("food")
    assert menu.values == ["food"]
    menu._toggle("food")
    assert menu.values == []


def test_filter_value_joins_selected_values():
    menu = _make_menu()
    menu._toggle("food")
    menu._toggle("weapons")
    assert menu.filter_value() == "food|weapons"


def test_clear_resets_values():
    menu = _make_menu()
    menu._toggle("food")
    menu.clear()
    assert menu.values == []
    assert menu.filter_value() == ""


def test_toggle_triggers_on_changed():
    menu = _make_menu()
    menu._toggle("food")
    menu._on_changed.assert_called_once()


def test_icon_uses_pets_in_cat_mode():
    normal = _make_menu(is_cat=lambda: False)
    cat = _make_menu(is_cat=lambda: True)
    assert normal._icon() == ft.Icons.CHECK
    assert cat._icon() == ft.Icons.PETS


def test_menu_exposes_submenu_button():
    menu = _make_menu()
    assert len(menu.menu.controls) == 1
    assert isinstance(menu.menu.controls[0], ft.SubmenuButton)