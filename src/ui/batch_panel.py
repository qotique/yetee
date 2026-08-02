from __future__ import annotations

from collections.abc import Callable

import flet as ft

from models.field_def import CATEGORIES, STATIC_FIELD_DEFS
from ui.chip_set import ChipSet


class BatchPanel:
    def __init__(
        self,
        page: ft.Page,
        tips_switcher: ft.Control,
        on_batch_apply: Callable[[str], object] | None = None,
    ):
        self._page = page
        self._tips_switcher = tips_switcher
        self._on_batch_apply = on_batch_apply
        self._usage_chipset: ChipSet | None = None
        self._value_chipset: ChipSet | None = None
        self._field_controls: dict[str, ft.Control] = {}
        self._flag_checkboxes: dict[str, ft.Checkbox] = {}
        self._save_buttons: list[ft.IconButton] = []
        self._cat_mode: bool = False
        self._header = ft.Text("", size=14, weight=ft.FontWeight.BOLD)
        self._container = ft.Column(spacing=4, scroll=ft.ScrollMode.AUTO)

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
        self._save_buttons = []
        self._container.controls = self._build_controls(flag_names)
        if self._cat_mode:
            self._apply_cat_icons()

    def _apply_cat_icons(self) -> None:
        icon = ft.Icons.PETS if self._cat_mode else ft.Icons.SAVE
        for btn in self._save_buttons:
            btn.icon = icon
            try:
                btn.update()
            except RuntimeError:
                pass
        if self._usage_chipset:
            self._usage_chipset.set_cat_mode(self._cat_mode)
        if self._value_chipset:
            self._value_chipset.set_cat_mode(self._cat_mode)

    def set_cat_mode(self, enabled: bool) -> None:
        self._cat_mode = enabled
        self._apply_cat_icons()

    def hide(self) -> None:
        self._usage_chipset = None
        self._value_chipset = None
        self._field_controls.clear()
        self._flag_checkboxes.clear()
        self._save_buttons.clear()
        self._container.controls = []

    def _build_controls(self, flag_names: list[str]) -> list[ft.Control]:
        controls: list[ft.Control] = [
            self._header,
            ft.Divider(height=4),
        ]

        for fd in STATIC_FIELD_DEFS:
            if fd.key == "name":
                continue
            w: ft.Control = ft.TextField(
                value="",
                dense=True,
                text_size=12,
                hint_text="",
                expand=True,
            )
            self._field_controls[fd.key] = w
            btn = ft.IconButton(
                icon=ft.Icons.SAVE,
                icon_size=18,
                tooltip=f"Set {fd.label}",
                on_click=lambda _, k=fd.key: self._on_save(k),
            )
            self._save_buttons.append(btn)
            controls.append(
                ft.Row(
                    [
                        ft.Text(fd.label, width=70, size=12),
                        w,
                        btn,
                    ],
                    spacing=4,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                )
            )

        cat_dd = ft.Dropdown(
            value="",
            dense=True,
            text_size=12,
            expand=True,
            options=[ft.DropdownOption(key="", text="")]
            + [ft.DropdownOption(key=c) for c in CATEGORIES],
        )
        self._field_controls["category"] = cat_dd
        cat_btn = ft.IconButton(
            icon=ft.Icons.SAVE,
            icon_size=18,
            tooltip="Set Category",
            on_click=lambda _: self._on_save("category"),
        )
        self._save_buttons.append(cat_btn)
        controls.append(
            ft.Row(
                [
                    ft.Text("Category", width=70, size=12),
                    cat_dd,
                    cat_btn,
                ],
                spacing=4,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            )
        )

        controls.append(ft.Divider(height=4))
        controls.append(ft.Text("Usage", size=12, weight=ft.FontWeight.BOLD))
        if self._usage_chipset:
            controls.append(self._usage_chipset.build_controls())
        usage_btn = ft.IconButton(
            icon=ft.Icons.SAVE,
            icon_size=18,
            tooltip="Apply Usage",
            on_click=lambda _: self._on_save("usage"),
        )
        self._save_buttons.append(usage_btn)
        controls.append(ft.Row([usage_btn]))

        controls.append(ft.Divider(height=4))
        controls.append(ft.Text("Value", size=12, weight=ft.FontWeight.BOLD))
        if self._value_chipset:
            controls.append(self._value_chipset.build_controls())
        value_btn = ft.IconButton(
            icon=ft.Icons.SAVE,
            icon_size=18,
            tooltip="Apply Value",
            on_click=lambda _: self._on_save("value"),
        )
        self._save_buttons.append(value_btn)
        controls.append(ft.Row([value_btn]))

        if flag_names:
            controls.append(ft.Divider(height=4))
            controls.append(ft.Text("Flags", size=12, weight=ft.FontWeight.BOLD))
            for fn in flag_names:
                cb = ft.Checkbox(label="", value=False)
                self._flag_checkboxes[fn] = cb
                flag_btn = ft.IconButton(
                    icon=ft.Icons.SAVE,
                    icon_size=18,
                    tooltip=f"Set {fn}",
                    on_click=lambda _, flag=fn: self._on_save(f"flag:{flag}"),
                )
                self._save_buttons.append(flag_btn)
                controls.append(
                    ft.Row(
                        [
                            ft.Text(f"  {fn}", width=130, size=12),
                            cb,
                            flag_btn,
                        ],
                        spacing=4,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    )
                )

        controls.append(ft.Container(expand=True))
        controls.append(self._tips_switcher)
        return controls

    def _on_save(self, key: str) -> None:
        if self._on_batch_apply:
            self._on_batch_apply(key)

    def build(self) -> ft.Control:
        return self._container

    def get_values(self) -> dict[str, object]:
        return {k: v.value for k, v in self._field_controls.items()}
