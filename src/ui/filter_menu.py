from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import cast

import flet as ft


@dataclass
class FilterSpec:
    key: str
    label: str
    options: list[str]
    empty_marker: str


class FilterMenu:
    def __init__(
        self,
        spec: FilterSpec,
        on_changed: Callable[[], None],
        is_cat: Callable[[], bool] | None = None,
    ) -> None:
        self._spec = spec
        self._on_changed = on_changed
        self._is_cat = is_cat or (lambda: False)
        self.values: list[str] = []
        self.menu = ft.MenuBar(
            style=ft.MenuStyle(
                fixed_size=ft.Size.from_height(32),
                shape=ft.RoundedRectangleBorder(radius=10),
            ),
            controls=[
                ft.SubmenuButton(
                    content=ft.Text(spec.label),
                    controls=self._build_items(),
                )
            ],
        )

    @property
    def spec(self) -> FilterSpec:
        return self._spec

    def _icon(self) -> ft.Icons:
        return cast(
            ft.Icons, ft.Icons.PETS if self._is_cat() else ft.Icons.CHECK
        )

    def _build_items(self) -> list[ft.MenuItemButton]:
        icon = self._icon()
        items = []
        for option in self._spec.options:
            items.append(
                ft.MenuItemButton(
                    content=ft.Text(option),
                    leading=ft.Icon(icon) if option in self.values else None,
                    on_click=lambda _, opt=option: self._toggle(opt),
                    close_on_click=False,
                )
            )
        empty_selected = self._spec.empty_marker in self.values
        items.append(
            ft.MenuItemButton(
                content=ft.Text("(empty)"),
                leading=ft.Icon(icon) if empty_selected else None,
                on_click=lambda _: self._toggle(self._spec.empty_marker),
                close_on_click=False,
            )
        )
        return items

    def _toggle(self, value: str) -> None:
        if value in self.values:
            self.values.remove(value)
        else:
            self.values.append(value)
        self.rebuild()
        self._on_changed()

    def rebuild(self) -> None:
        for ctrl in self.menu.controls:
            if isinstance(ctrl, ft.SubmenuButton):
                ctrl.controls = self._build_items()
                ctrl.update()

    def clear(self) -> None:
        self.values.clear()
        self.rebuild()

    def filter_value(self) -> str:
        return "|".join(self.values)