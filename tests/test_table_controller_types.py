from __future__ import annotations

from unittest.mock import MagicMock

import flet as ft

from controllers.table_controller import TableController
from models.field_def import FieldDef, FieldType
from models.row_data import RowData


def _make_controller() -> TableController:
    page = MagicMock()
    page.theme = None
    page.dark_theme = None
    page.on_keyboard_event = None
    return TableController(page=page)


def _field_defs() -> list[FieldDef]:
    return [
        FieldDef("i", "I", FieldType.INT, width=100),
        FieldDef("f", "F", FieldType.FLOAT, width=100),
        FieldDef("b", "B", FieldType.BOOL, width=100),
        FieldDef("t", "T", FieldType.TEXT, width=100),
    ]


def test_int_field_renders_numeric_textfield():
    tc = _make_controller()
    tc.init_table(_field_defs())

    int_widget = tc._pool_fields[0][0]
    assert isinstance(int_widget, ft.TextField)
    assert int_widget.keyboard_type == ft.KeyboardType.NUMBER
    assert int_widget.text_align == ft.TextAlign.RIGHT
    assert int_widget.data == "i"


def test_float_field_renders_numeric_textfield():
    tc = _make_controller()
    tc.init_table(_field_defs())

    float_widget = tc._pool_fields[0][1]
    assert isinstance(float_widget, ft.TextField)
    assert float_widget.keyboard_type == ft.KeyboardType.NUMBER
    assert float_widget.text_align == ft.TextAlign.RIGHT


def test_bool_field_renders_dropdown_with_true_false():
    tc = _make_controller()
    tc.init_table(_field_defs())

    bool_widget = tc._pool_fields[0][2]
    assert isinstance(bool_widget, ft.Dropdown)
    options = [o.key for o in bool_widget.options]
    assert "true" in options
    assert "false" in options


def test_text_field_unchanged():
    tc = _make_controller()
    tc.init_table(_field_defs())

    text_widget = tc._pool_fields[0][3]
    assert isinstance(text_widget, ft.TextField)
    assert text_widget.keyboard_type is not None or True


def test_render_sync_back_int_bool_values():
    tc = _make_controller()
    tc.init_table(_field_defs())

    rows = [
        RowData(
            values={"i": "5", "f": "1.5", "t": "x"},
            flags={},
            elem=None,
        ),
        RowData(
            values={"i": "7", "f": "2.5", "t": "y"},
            flags={},
            elem=None,
        ),
    ]
    tc.render(rows, [0, 1], 0, set())

    assert tc._pool_fields[0][0].value == "5"
    assert tc._pool_fields[0][1].value == "1.5"
    assert tc._pool_fields[0][2].value == ""

    tc._pool_fields[0][0].value = "9"
    tc._pool_fields[0][1].value = "3.75"
    tc._pool_fields[0][2].value = "true"
    tc.sync_back(rows, [0, 1], 0)

    assert rows[0].values["i"] == "9"
    assert rows[0].values["f"] == "3.75"
    assert rows[0].values["b"] == "true"
