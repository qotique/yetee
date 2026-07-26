from __future__ import annotations

from collections.abc import Callable

import flet as ft


class ChipSet:
    def __init__(
        self,
        values: list[str],
        options: list[str],
        label: str = "",
        on_change: Callable | None = None,
    ):
        self._values = set(values)
        self._options = options
        self._label = label
        self._on_change = on_change

        self._chips_row = ft.Row(wrap=True, spacing=4, run_spacing=4)
        self._add_dd = ft.Dropdown(
            value="",
            dense=True,
            text_size=12,
            expand=True,
            options=[ft.DropdownOption(key="", text="")] + [ft.DropdownOption(key=o) for o in self._options],
        )
        self._add_btn = ft.FilledButton("Add", on_click=self._handle_add)
        self._container = ft.Column(scroll=ft.ScrollMode.AUTO, height=100)
        self.refresh()

    def add(self, value: str) -> None:
        if value:
            self._values.add(value)
            if self._on_change:
                self._on_change()
            self.refresh()

    def remove(self, value: str) -> None:
        self._values.discard(value)
        if self._on_change:
            self._on_change()
        self.refresh()

    def get_values(self) -> list[str]:
        return sorted(self._values)

    def _handle_add(self, e) -> None:
        v = self._add_dd.value
        if v:
            self.add(v)
            self._add_dd.value = ""

    def build_controls(self) -> ft.Control:
        self.refresh()
        self._container.controls = [
            self._chips_row,
            ft.Row([self._add_dd, self._add_btn], spacing=4),
        ]
        return self._container

    def refresh(self) -> None:
        self._chips_row.controls = [
            ft.Chip(label=ft.Text(s), on_delete=lambda _, v=s: self.remove(v))
            for s in sorted(self._values)
        ]
