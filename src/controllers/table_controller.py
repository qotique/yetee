from __future__ import annotations

from collections.abc import Callable
import logging

import flet as ft

from models.field_def import CATEGORIES, FieldDef, FieldType, STATIC_FIELD_DEFS
from models.row_data import RowData

logger = logging.getLogger(__name__)

PAGE_SIZE = 50

DEFAULT_FLAG_NAMES = [
    "count_in_cargo",
    "count_in_hoarder",
    "count_in_map",
    "count_in_player",
    "crafted",
    "deloot",
]

FIELD_TIPS = {
    "name": "The item ClassName used in the XML file",
    "nominal": "The global target quantity the economy maintains across the map",
    "lifetime": "How long items persist before despawning (seconds)",
    "restock": "The interval between economy replenishment checks (seconds)",
    "min": "The absolute minimum quantity that must exist in the economy",
    "quantmin": "Minimum spawn count per loot position or container",
    "quantmax": "Maximum spawn count per loot position or container",
    "cost": "Spawn priority; higher values increase spawn priority",
    "category": "Classifies items for loot table filtering",
}


def _collect_flag_names(rows: list[RowData]) -> list[str]:
    seen: set[str] = set(DEFAULT_FLAG_NAMES)
    for r in rows:
        seen.update(r.flags.keys())
    return sorted(seen)


class TableController:
    def __init__(self, page: ft.Page):
        self._page = page

        self._field_defs: list[FieldDef] = []
        self._flag_names: list[str] = []
        self._col_widths: list[int] = []
        self._pool_fields: list[list[ft.Control]] = []
        self._pool_rows: list[ft.Container] = []

        self._header_row = ft.Row(spacing=6)
        self._body_column = ft.Column(spacing=0, scroll=ft.ScrollMode.AUTO, expand=True)
        self._table_inner = ft.Column(
            [
                self._header_row,
                ft.Divider(height=1, color=ft.Colors.OUTLINE_VARIANT),
                self._body_column,
            ],
            spacing=0,
        )

        self._on_row_click_cb: Callable[[int], None] | None = None
        self._on_field_change_cb: Callable[[object], None] | None = None
        self._on_row_hover_cb: Callable[[object, int], None] | None = None
        self._on_row_tap_down_cb: Callable[[object, int], None] | None = None
        self._prev_count: int = 0

    def set_callbacks(
        self,
        on_row_click: Callable[[int], None] | None = None,
        on_field_change: Callable[[object], None] | None = None,
        on_row_hover: Callable[[object, int], None] | None = None,
        on_row_tap_down: Callable[[object, int], None] | None = None,
    ) -> None:
        self._on_row_click_cb = on_row_click
        self._on_field_change_cb = on_field_change
        self._on_row_hover_cb = on_row_hover
        self._on_row_tap_down_cb = on_row_tap_down

    def get_table_widget(self) -> ft.Column:
        return self._table_inner

    @property
    def flag_names(self) -> list[str]:
        return self._flag_names

    @flag_names.setter
    def flag_names(self, value: list[str]) -> None:
        self._flag_names = value

    @property
    def field_defs(self) -> list[FieldDef]:
        return self._field_defs

    @property
    def pool_fields(self) -> list[list[ft.Control]]:
        return self._pool_fields

    @property
    def pool_rows(self) -> list[ft.Container]:
        return self._pool_rows

    def init_dynamic(self) -> None:
        self._field_defs = list(STATIC_FIELD_DEFS)

        for fn in self._flag_names:
            width = max(60, len(fn) * 8 + 24)
            self._field_defs.append(FieldDef(fn, fn, FieldType.FLAG, width=width))

        self._field_defs.append(
            FieldDef(
                "category",
                "Category",
                FieldType.SINGLE_NAMED,
                width=150,
                options=CATEGORIES,
            )
        )

        self._col_widths = [fd.width for fd in self._field_defs]
        table_width = sum(self._col_widths) + (len(self._field_defs) - 1) * 6

        align_right = ft.TextAlign.RIGHT
        header_cells = []
        for fd in self._field_defs:
            text_align = align_right if fd.align == align_right else ft.TextAlign.LEFT
            cell_align = (
                ft.Alignment.CENTER_RIGHT
                if text_align == align_right
                else ft.Alignment.CENTER_LEFT
            )
            hc = ft.Container(
                content=ft.Text(
                    fd.label, size=12, weight=ft.FontWeight.BOLD, text_align=text_align
                ),
                width=fd.width,
                height=36,
                alignment=cell_align,
                padding=ft.Padding(left=12, right=12, top=0, bottom=0),
                tooltip=FIELD_TIPS.get(fd.key, f"{fd.label} field"),
            )
            header_cells.append(hc)
        self._header_row.controls = header_cells
        self._table_inner.width = table_width

        self._pool_fields = []
        self._pool_rows = []

        for ri in range(PAGE_SIZE):
            fields: list[ft.Control] = []
            row_cells: list[ft.Container] = []
            for ci, fd in enumerate(self._field_defs):
                if fd.is_single_named():
                    w = ft.Dropdown(
                        value="",
                        dense=True,
                        text_size=12,
                        height=36,
                        content_padding=ft.Padding(left=12, top=2, right=12, bottom=2),
                        border_color=ft.Colors.with_opacity(0.5, ft.Colors.OUTLINE),
                        focused_border_color=ft.Colors.PRIMARY,
                        filled=False,
                        options=[ft.DropdownOption(key="", text="")]
                        + [ft.DropdownOption(key=c) for c in (fd.options or [])],
                        on_select=self._on_field_change,
                        hover_color=ft.Colors.TRANSPARENT,
                        on_focus=lambda e, idx=ri: self._trigger_row_click(idx),
                        expand=True,
                    )
                elif fd.is_flag():
                    w = ft.Checkbox(
                        label="",
                        value=False,
                        on_change=self._on_field_change,
                        on_focus=lambda e, idx=ri: self._trigger_row_click(idx),
                    )
                else:
                    w = ft.TextField(
                        value="",
                        dense=True,
                        text_size=12,
                        text_align=fd.align,
                        min_lines=1,
                        max_lines=1,
                        on_change=self._on_field_change,
                        hover_color=ft.Colors.TRANSPARENT,
                        filled=False,
                        on_focus=lambda e, idx=ri: self._trigger_row_click(idx),
                        on_click=lambda e, idx=ri: self._trigger_row_click(idx),
                        expand=True,
                    )
                w.data = fd.key
                w.tooltip = FIELD_TIPS.get(fd.key, f"{fd.label} field")
                fields.append(w)

                if fd.is_flag():
                    cell = ft.Container(
                        content=ft.Row([w], alignment=ft.MainAxisAlignment.CENTER),
                        width=fd.width,
                        alignment=ft.Alignment.CENTER,
                    )
                else:
                    cell = ft.Container(content=w, width=fd.width)

                row_cells.append(cell)

            self._pool_fields.append(fields)
            self._pool_rows.append(
                ft.Container(
                    content=ft.Row(row_cells, spacing=6),
                    bgcolor=None,
                    border=ft.border.Border(
                        bottom=ft.border.BorderSide(
                            1,
                            ft.Colors.with_opacity(
                                0.12,
                                ft.Colors.OUTLINE_VARIANT,
                            ),
                        ),
                    ),
                    on_click=lambda e, idx=ri: self._trigger_row_click(idx),
                    on_hover=lambda e, idx=ri: self._trigger_row_hover(e, idx),
                    on_tap_down=lambda e, idx=ri: self._trigger_row_tap_down(e, idx),
                )
            )

        logger.debug(
            "Table pool initialized: %d rows x %d cols",
            PAGE_SIZE,
            len(self._field_defs),
        )

    def _on_field_change(self, e: object) -> None:
        if self._on_field_change_cb:
            self._on_field_change_cb(e)

    def _trigger_row_click(self, pool_slot: int) -> None:
        if self._on_row_click_cb:
            self._on_row_click_cb(pool_slot)

    def _trigger_row_hover(self, e: object, pool_slot: int) -> None:
        if self._on_row_hover_cb:
            self._on_row_hover_cb(e, pool_slot)

    def _trigger_row_tap_down(self, e: object, pool_slot: int) -> None:
        if self._on_row_tap_down_cb:
            self._on_row_tap_down_cb(e, pool_slot)

    def render(
        self,
        rows: list[RowData],
        filtered: list[int],
        page_idx: int,
        selected_indices: set[int],
    ) -> None:
        syncing = getattr(self, "_syncing", False)
        start = page_idx * PAGE_SIZE
        end = min(start + PAGE_SIZE, len(filtered))
        count = end - start

        for i in range(count):
            actual_idx = filtered[start + i]
            row_data = rows[actual_idx]
            self._pool_rows[i].bgcolor = (
                ft.Colors.PRIMARY_CONTAINER if actual_idx in selected_indices else None
            )
            for j, fd in enumerate(self._field_defs):
                field = self._pool_fields[i][j]
                if fd.is_flag():
                    val = row_data.flags.get(fd.key, "0") == "1"
                    if field.value != val:
                        field.value = val
                else:
                    in_val = row_data.values.get(fd.key, "")
                    if field.value != in_val:
                        field.value = in_val

        if self._prev_count != count:
            self._body_column.controls = self._pool_rows[:count]
            self._prev_count = count

    def sync_back(
        self, rows: list[RowData], filtered: list[int], page_idx: int
    ) -> None:
        start = page_idx * PAGE_SIZE
        for i in range(len(self._body_column.controls)):
            row_idx = filtered[start + i] if start + i < len(filtered) else -1
            if row_idx < 0:
                break
            row_data = rows[row_idx]
            for j, fd in enumerate(self._field_defs):
                widget = self._pool_fields[i][j]
                if fd.is_flag():
                    row_data.flags[fd.key] = "1" if widget.value else "0"
                else:
                    row_data.values[fd.key] = widget.value

    def clear(self) -> None:
        self._field_defs = []
        self._flag_names = []
        self._header_row.controls = []
        self._body_column.controls = []
        self._col_widths = []
        self._pool_fields = []
        self._pool_rows = []
        self._prev_count = 0
