from __future__ import annotations

from collections.abc import Callable

import flet as ft

from models.field_def import STATIC_FIELD_DEFS
from ui.chip_set import ChipSet

CATEGORIES = ["clothes", "containers", "explosives", "food", "lootdispatch", "tools", "weapons"]


class BatchPanel:
    def __init__(
        self,
        page: ft.Page,
        tips_switcher: ft.Control,
        on_batch_apply: Callable | None = None,
    ):
        self._page = page
        self._tips_switcher = tips_switcher
        self._on_batch_apply = on_batch_apply
        self._usage_chipset: ChipSet | None = None
        self._value_chipset: ChipSet | None = None
        self._field_controls: dict[str, ft.Control] = {}
        self._flag_checkboxes: dict[str, ft.Checkbox] = {}
        self._header = ft.Text("", size=14, weight=ft.FontWeight.BOLD)
        self._container = ft.Column(spacing=4)

    def show(
        self,
        header_text: str,
        usage_options: list[str],
        value_options: list[str],
        flag_names: list[str],
    ) -> None:
        self._header.value = header_text
        self._usage_chipset = ChipSet([], usage_options, on_change=None)
        self._value_chipset = ChipSet([], value_options, on_change=None)
        self._field_controls = {}
        self._flag_checkboxes = {}
        self._container.controls = self._build_controls(flag_names)

    def hide(self) -> None:
        self._usage_chipset = None
        self._value_chipset = None
        self._field_controls.clear()
        self._flag_checkboxes.clear()
        self._container.controls = []

    def _build_controls(self, flag_names: list[str]) -> list[ft.Control]:
        controls: list[ft.Control] = [
            self._header,
            ft.Divider(height=4),
        ]

        for fd in STATIC_FIELD_DEFS:
            if fd.key == "name":
                continue
            w: ft.Control = ft.TextField(value="", dense=True, text_size=12, hint_text="", expand=True)
            self._field_controls[fd.key] = w
            controls.append(ft.Row([
                ft.Text(fd.label, width=70, size=12),
                w,
                ft.IconButton(
                    icon=ft.Icons.SAVE, icon_size=18, tooltip=f"Set {fd.label}",
                    on_click=lambda _, k=fd.key: self._on_save(k),
                ),
            ], spacing=4, vertical_alignment=ft.CrossAxisAlignment.CENTER))

        cat_dd = ft.Dropdown(
            value="", dense=True, text_size=12,
            expand=True,
            options=[ft.DropdownOption(key="", text="")] + [ft.DropdownOption(key=c) for c in CATEGORIES],
        )
        self._field_controls["category"] = cat_dd
        controls.append(ft.Row([
            ft.Text("Category", width=70, size=12),
            cat_dd,
            ft.IconButton(
                icon=ft.Icons.SAVE, icon_size=18, tooltip="Set Category",
                on_click=lambda _: self._on_save("category"),
            ),
        ], spacing=4, vertical_alignment=ft.CrossAxisAlignment.CENTER))

        controls.append(ft.Divider(height=4))
        controls.append(ft.Text("Usage", size=12, weight=ft.FontWeight.BOLD))
        if self._usage_chipset:
            controls.append(self._usage_chipset.build_controls())
        controls.append(ft.Row([
            ft.IconButton(
                icon=ft.Icons.SAVE, icon_size=18, tooltip="Apply Usage",
                on_click=lambda _: self._on_save("usage"),
            ),
        ]))

        controls.append(ft.Divider(height=4))
        controls.append(ft.Text("Value", size=12, weight=ft.FontWeight.BOLD))
        if self._value_chipset:
            controls.append(self._value_chipset.build_controls())
        controls.append(ft.Row([
            ft.IconButton(
                icon=ft.Icons.SAVE, icon_size=18, tooltip="Apply Value",
                on_click=lambda _: self._on_save("value"),
            ),
        ]))

        if flag_names:
            controls.append(ft.Divider(height=4))
            controls.append(ft.Text("Flags", size=12, weight=ft.FontWeight.BOLD))
            for fn in flag_names:
                cb = ft.Checkbox(label="", value=False)
                self._flag_checkboxes[fn] = cb
                controls.append(ft.Row([
                    ft.Text(f"  {fn}", width=130, size=12),
                    cb,
                    ft.IconButton(
                        icon=ft.Icons.SAVE, icon_size=18, tooltip=f"Set {fn}",
                        on_click=lambda _, flag=fn: self._on_save(f"flag:{flag}"),
                    ),
                ], spacing=4, vertical_alignment=ft.CrossAxisAlignment.CENTER))

        controls.append(ft.Container(expand=True))
        controls.append(self._tips_switcher)
        return controls

    def _on_save(self, key: str) -> None:
        if self._on_batch_apply:
            self._on_batch_apply(key)

    def build(self) -> ft.Control:
        return self._container

    def get_values(self) -> dict:
        return {k: v.value for k, v in self._field_controls.items()}
