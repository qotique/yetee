from __future__ import annotations

from collections.abc import Callable

import flet as ft

from models.row_data import RowData
from ui.chip_set import ChipSet


class DetailPanel:
    def __init__(
        self,
        page: ft.Page,
        tips_switcher: ft.Control,
        on_changed: Callable | None = None,
    ):
        self._page = page
        self._tips_switcher = tips_switcher
        self._on_changed = on_changed
        self._selected_row: RowData | None = None
        self._usage_chipset: ChipSet | None = None
        self._value_chipset: ChipSet | None = None
        self._header = ft.Text("", size=14, weight=ft.FontWeight.BOLD)
        self._container = ft.Column()

    def show(self, row: RowData, usage_options: list[str], value_options: list[str]) -> None:
        self._selected_row = row
        usage_values = [x.strip() for x in row.values.get("usage", "").split(",") if x.strip()]
        value_values = [x.strip() for x in row.values.get("value", "").split(",") if x.strip()]
        self._usage_chipset = ChipSet(usage_values, usage_options, on_change=self._on_changed)
        self._value_chipset = ChipSet(value_values, value_options, on_change=self._on_changed)
        self._header.value = f"Selected: {row.values['name']}"
        self.refresh()

    def hide(self) -> None:
        self._selected_row = None
        self._usage_chipset = None
        self._value_chipset = None
        self._container.controls = []

    def refresh(self) -> None:
        controls: list[ft.Control] = [
            self._header,
            ft.Divider(height=8),
            ft.Text("Usage", size=12, weight=ft.FontWeight.BOLD),
        ]
        if self._usage_chipset:
            controls.append(self._usage_chipset.build_controls())
        controls.extend([
            ft.Divider(height=8),
            ft.Text("Value", size=12, weight=ft.FontWeight.BOLD),
        ])
        if self._value_chipset:
            controls.append(self._value_chipset.build_controls())
        controls.extend([
            ft.Divider(height=8),
            ft.Container(expand=True),
            self._tips_switcher,
        ])
        self._container.controls = controls

    def build(self) -> ft.Control:
        return self._container
