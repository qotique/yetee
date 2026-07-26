from __future__ import annotations

import asyncio
import time

from lxml import etree as ET

import flet as ft

from models.field_def import FieldDef, FieldType, STATIC_FIELD_DEFS
from models.row_data import RowData
from repository.file_cache import FileCache
from repository.xml_repository import XmlRepository, _elem_text, _set_elem_text, _names_to_str
from models.undo_manager import UndoManager
from ui.batch_panel import BatchPanel
from ui.detail_panel import DetailPanel


CATEGORIES = ["clothes", "containers", "explosives", "food", "lootdispatch", "tools", "weapons"]
USAGES = ["Coast", "ContaminatedArea", "Farm", "Firefighter", "Historical", "Hunting", "Industrial", "Lunapark", "Medic", "Military", "Office", "Police", "Prison", "School", "SeasonalEvent", "Town", "Village"]
VALUES_LIST = ["Tier0", "Tier1", "Tier2", "Tier3", "Tier4", "Unique"]

_TIPS = [
    "Nominal is the global target quantity the economy maintains across the map",
    "Lifetime (seconds) controls how long items persist before despawning",
    "Restock (seconds) is the interval between economy replenishment checks",
    "Min sets the absolute minimum quantity that must exist in the economy",
    "QuantMin / QuantMax control spawn count per loot position or container",
    "Cost = -1 prevents natural spawning; higher values increase spawn priority",
    "Flag checkboxes control where items spawn (cargo, map, player, hoarder, etc.)",
    "Category classifies items (clothes, weapons, food) for loot table filtering",
    "Usage values (Military, Industrial, Town, etc.) define spawn locations",
    "Value tiers control rarity distribution across loot circles",
    "Items with no Usage values will not spawn naturally anywhere",
    "Cost = 0 is default priority; lower cost items spawn more frequently",
    "Too high Lifetime can clutter the world; too low causes rapid despawn",
    "Set Nominal too high and items pile up; too low and they are scarce",
    "Add multiple Usage values to allow spawning in several location types",
    "Click any cell in a row to select it and edit details in the right panel",
    "Search filters types by name as you type — use the bar below the table",
    "Category values come from a dropdown with common DayZ categories",
    "Add Usage/Value chips using the + buttons in the right panel",
    "Remove a chip by clicking the X on it",
    "Click Save to persist all changes to the XML file",
    "Use Prev and Next buttons to navigate between pages of results",
    "Edits are tracked as dirty until you click Save",
]


PAGE_SIZE = 50

def _collect_flag_names(rows: list[RowData]) -> list[str]:
    seen: set[str] = set()
    for r in rows:
        seen.update(r.flags.keys())
    return sorted(seen)


class FileDisplay:
    def __init__(
        self,
        page: ft.Page,
        xml_repo: XmlRepository | None = None,
        cache: FileCache | None = None,
        detail_panel: DetailPanel | None = None,
        batch_panel: BatchPanel | None = None,
    ):
        self._page = page
        self.cache = cache or FileCache()
        self.xml_repo = xml_repo or XmlRepository(cache=self.cache)
        self._undo_mgr = UndoManager()
        self._page.theme = ft.Theme(hover_color=ft.Colors.TRANSPARENT)
        self._page.dark_theme = ft.Theme(hover_color=ft.Colors.TRANSPARENT)
        self._search_task: asyncio.Task | None = None
        self._tip_task: asyncio.Task | None = None
        self._path: str | None = None
        self._rows: list[RowData] = []
        self._filtered: list[int] = []
        self._page_idx: int = 0
        self._dirty: bool = False
        self._syncing: bool = False
        self._prev_count: int = 0

        self._selected_row_idx: int | None = None
        self._selected_row_indices: set[int] = set()
        self._multi_select_mode: bool = False
        self._shift_pressed: bool = False
        self._mouse_down: bool = False
        self._last_clicked_row: int | None = None
        self._drag_start_slot: int | None = None

        page.on_keyboard_event = self._on_page_keyboard

        self._field_defs: list[FieldDef] = []
        self._flag_names: list[str] = []
        self._pool_fields: list[list] = []
        self._pool_rows: list[ft.Container] = []

        self._save_status = ft.Text("", size=12)
        self._page_info = ft.Text("", size=12)
        self._prev_btn = ft.Button("Prev", on_click=self._prev_page)
        self._next_btn = ft.Button("Next", on_click=self._next_page)
        self._multi_btn = ft.Button(
            "Multi-select disabled",
            icon=ft.Icons.SELECT_ALL,
            tooltip="Toggle multi-select mode",
            on_click=self._toggle_multi_select,
            icon_color=ft.Colors.GREY,
        )
        self._undo_btn = ft.IconButton(
            icon=ft.Icons.UNDO,
            on_click=self._on_undo,
        )
        self._redo_btn = ft.IconButton(
            icon=ft.Icons.REDO,
            on_click=self._on_redo,
        )
        self._search_field = ft.TextField(
            label="Search",
            icon=ft.Icons.SEARCH,
            dense=True,
            text_size=12,
            width=250,
            on_submit=self._on_search,
            on_change=self._on_search_changed,
        )
        self._filter_category_field = ft.TextField(
            label="category",
            icon=ft.Icons.CATEGORY,
            dense=True,
            text_size=8,
            width=200,
            on_submit=self._on_search,
            on_change=self._on_filter_changed,
        )
        self._filter_usage_field = ft.TextField(
            label="usage",
            icon=ft.Icons.MAPS_HOME_WORK,
            dense=True,
            text_size=6,
            width=200,
            on_submit=self._on_search,
            on_change=self._on_filter_changed,
        )
        self._filter_value_field = ft.TextField(
            label="value",
            icon=ft.Icons.EDIT_LOCATION,
            dense=True,
            text_size=6,
            width=200,
            on_submit=self._on_search,
            on_change=self._on_filter_changed,
        )

        self._header_row = ft.Row(spacing=6)
        self._body_column = ft.Column(spacing=0, scroll=ft.ScrollMode.AUTO, expand=True)
        self._table_inner = ft.Column(
            [self._header_row, ft.Divider(height=1, color=ft.Colors.OUTLINE_VARIANT), self._body_column],
            spacing=0,
        )
        self._col_widths: list[int] = []

        self._tips_switcher = ft.AnimatedSwitcher(
            content=ft.Text(_TIPS[0], size=11, italic=True, color=ft.Colors.GREY_500),
            transition=ft.AnimatedSwitcherTransition.FADE,
            duration=500,
        )
        self._detail_placeholder = ft.Container(
            content=ft.Column([
                ft.Text("Select type", size=16, italic=True, color=ft.Colors.GREY, text_align=ft.TextAlign.CENTER),
                ft.Container(expand=True),
                self._tips_switcher,
            ]),
            alignment=ft.Alignment.CENTER,
            expand=True,
        )
        self._detail_panel = detail_panel or DetailPanel(self._page, self._tips_switcher, on_changed=lambda: self._on_field_change(None))
        self._batch_panel = batch_panel or BatchPanel(self._page, self._tips_switcher, on_batch_apply=self._on_batch_action)
        self._detail_container = ft.Container(
            width=400,
            padding=10,
            content=self._detail_placeholder,
        )

        self.control = ft.Container(
            visible=False,
            expand=True,
            content=ft.KeyboardListener(
                autofocus=True,
                on_key_down=self._on_key_down,
                on_key_up=self._on_key_up,
                content=ft.Column(
                    [
                        ft.Row(
                            [
                                ft.Button("Save", icon=ft.Icons.SAVE, on_click=self._save),
                                self._multi_btn,
                                self._undo_btn,
                                self._redo_btn,
                                ft.Divider(),
                                self._save_status,
                            ],
                            alignment=ft.MainAxisAlignment.START,
                        ),
                        ft.Row(
                            [
                        ft.Container(
                            content=ft.Column(
                                [
                                    ft.Row(
                                        [self._table_inner],
                                        scroll=ft.ScrollMode.ALWAYS,
                                        expand=True,
                                        vertical_alignment=ft.CrossAxisAlignment.STRETCH,
                                    ),
                                ],
                                expand=True,
                                spacing=0,
                            ),
                            border=ft.border.Border(
                                ft.border.BorderSide(1, ft.Colors.OUTLINE_VARIANT),
                                ft.border.BorderSide(1, ft.Colors.OUTLINE_VARIANT),
                                ft.border.BorderSide(1, ft.Colors.OUTLINE_VARIANT),
                                ft.border.BorderSide(1, ft.Colors.OUTLINE_VARIANT),
                            ),
                            border_radius=8,
                            expand=True,
                        ),
                                self._detail_container,
                            ],
                            expand=True,
                        ),
                        ft.Row(
                            [
                                self._prev_btn,
                                self._page_info,
                                self._next_btn,
                                self._search_field,
                                ft.Divider(),
                                self._filter_category_field,
                                self._filter_usage_field,
                                self._filter_value_field,
                            ],
                            alignment=ft.MainAxisAlignment.CENTER,
                        ),
                    ],
                    expand=True,
                ),
            ),
        )

    def _init_dynamic(self) -> None:
        self._field_defs = list(STATIC_FIELD_DEFS)

        for fn in self._flag_names:
            width = max(60, len(fn) * 8 + 24)
            self._field_defs.append(FieldDef(fn, fn, FieldType.FLAG, width=width))

        self._field_defs.append(FieldDef(
            "category", "Category", FieldType.SINGLE_NAMED,
            width=150, options=CATEGORIES,
        ))

        self._col_widths = [fd.width for fd in self._field_defs]
        table_width = sum(self._col_widths) + (len(self._field_defs) - 1) * 6

        align_right = ft.TextAlign.RIGHT
        header_cells = []
        for fd in self._field_defs:
            text_align = align_right if fd.align == align_right else ft.TextAlign.LEFT
            cell_align = ft.Alignment.CENTER_RIGHT if text_align == align_right else ft.Alignment.CENTER_LEFT
            hc = ft.Container(
                content=ft.Text(fd.label, size=12, weight=ft.FontWeight.BOLD, text_align=text_align),
                width=fd.width,
                height=36,
                alignment=cell_align,
                padding=ft.Padding(left=12, right=12, top=0, bottom=0),
            )
            header_cells.append(hc)
        self._header_row.controls = header_cells
        self._table_inner.width = table_width

        self._pool_fields = []
        self._pool_rows = []

        for ri in range(PAGE_SIZE):
            fields = []
            row_cells = []
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
                        options=[ft.DropdownOption(key="", text="")] + [ft.DropdownOption(key=c) for c in (fd.options or [])],
                        on_select=self._on_field_change,
                        hover_color=ft.Colors.TRANSPARENT,
                        on_focus=lambda e, idx=ri: self._on_row_click(idx),
                        expand=True,
                    )
                elif fd.is_flag():
                    w = ft.Checkbox(
                        label="",
                        value=False,
                        on_change=self._on_field_change,
                        on_focus=lambda e, idx=ri: self._on_row_click(idx),
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
                        on_focus=lambda e, idx=ri: self._on_row_click(idx),
                        on_click=lambda e, idx=ri: self._on_row_click(idx),
                        expand=True,
                    )
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
            self._pool_rows.append(ft.Container(
                content=ft.Row(row_cells, spacing=6),
                bgcolor=None,
                border=ft.border.Border(
                    bottom=ft.border.BorderSide(1, ft.Colors.with_opacity(0.12, ft.Colors.OUTLINE_VARIANT)),
                ),
                on_click=lambda e, idx=ri: self._on_row_click(idx),
                on_hover=lambda e, idx=ri: self._on_row_hover(e, idx),
                on_tap_down=lambda e, idx=ri: self._on_row_tap_down(e, idx),
            ))

    def load_file(self, path: str) -> None:
        self._path = path
        self._save_status.value = ""
        self._page_idx = 0
        self._search_field.value = ""
        self._filter_category_field.value = ""
        self._filter_usage_field.value = ""
        self._filter_value_field.value = ""
        self._dirty = False
        self._prev_count = 0
        self._undo_mgr.clear()

        try:
            self._rows = self.xml_repo.parse_file(path)
        except Exception as ex:
            self._undo_mgr.clear()
            self.control.content = ft.Container(
                content=ft.Text(f"Error parsing file: {ex}", selectable=True),
                padding=10,
            )
            self.control.visible = True
            return

        self._undo_mgr.record(self._undo_mgr.take_snapshot(self._rows))

        self._flag_names = _collect_flag_names(self._rows)
        self._init_dynamic()
        self._batch_panel.hide()
        self._detail_panel.hide()

        self._clear_selection()
        self._apply_filter("")
        self._render_page()
        self._refresh_button_states()
        self.control.visible = True

        if self._tip_task is not None and not self._tip_task.done():
            self._tip_task.cancel()
        self._tip_task = asyncio.create_task(self._cycle_tip())

    async def _cycle_tip(self) -> None:
        idx = 0
        while True:
            try:
                await asyncio.sleep(6)
            except asyncio.CancelledError:
                return
            idx = (idx + 1) % len(_TIPS)
            self._tips_switcher.content = ft.Text(_TIPS[idx], size=11, italic=True, color=ft.Colors.GREY_500)
            self._tips_switcher.update()

    def _on_field_change(self, e) -> None:
        if not self._syncing:
            self._dirty = True

    def _on_key_down(self, e: ft.KeyDownEvent) -> None:
        if "shift" in e.key.lower():
            self._shift_pressed = True

    def _on_key_up(self, e: ft.KeyUpEvent) -> None:
        if "shift" in e.key.lower():
            self._shift_pressed = False
            self._mouse_down = False

    def _on_page_keyboard(self, e: ft.KeyboardEvent) -> None:
        self._shift_pressed = e.shift
        if not e.shift:
            self._mouse_down = False

    def _toggle_multi_select(self, e) -> None:
        self._multi_select_mode = not self._multi_select_mode
        self._multi_btn.content = (
            ft.Text("Multi-select enabled")
            if self._multi_select_mode
            else ft.Text("Multi-select disabled")
        )
        self._multi_btn.icon_color = ft.Colors.PRIMARY if self._multi_select_mode else ft.Colors.GREY
        self._multi_btn.update()

    def _on_row_click(self, pool_slot: int) -> None:
        start = self._page_idx * PAGE_SIZE
        actual_idx = self._filtered[start + pool_slot] if start + pool_slot < len(self._filtered) else -1
        if actual_idx < 0:
            return
        if actual_idx == self._last_clicked_row and time.monotonic() - getattr(self, '_last_click_time', 0) < 0.1:
            return
        self._last_clicked_row = actual_idx
        self._last_click_time = time.monotonic()
        self._mouse_down = False
        self._sync_page_back()
        self._sync_detail_panel()
        if self._shift_pressed or self._multi_select_mode:
            if actual_idx in self._selected_row_indices:
                self._selected_row_indices.discard(actual_idx)
            else:
                self._selected_row_indices.add(actual_idx)
                self._selected_row_idx = actual_idx
            if len(self._selected_row_indices) == 1:
                self._load_detail_panel()
        else:
            self._selected_row_indices = {actual_idx}
            self._selected_row_idx = actual_idx
            self._load_detail_panel()
        self._update_detail_panel()
        self._render_page()
        self.control.update()

    def _on_row_tap_down(self, e, pool_slot: int) -> None:
        self._mouse_down = True
        self._drag_start_slot = pool_slot

    def _on_row_hover(self, e, pool_slot: int) -> None:
        if not e.data:
            return
        if not self._shift_pressed or not self._mouse_down:
            return
        start = self._page_idx * PAGE_SIZE

        if self._drag_start_slot is not None:
            start_idx = self._filtered[start + self._drag_start_slot] if start + self._drag_start_slot < len(self._filtered) else -1
            self._drag_start_slot = None
            if start_idx >= 0 and start_idx not in self._selected_row_indices:
                self._selected_row_indices.add(start_idx)
                self._selected_row_idx = start_idx
                self._render_page()
                self.control.update()

        actual_idx = self._filtered[start + pool_slot] if start + pool_slot < len(self._filtered) else -1
        if actual_idx < 0 or actual_idx in self._selected_row_indices:
            return
        self._sync_page_back()
        self._sync_detail_panel()
        self._selected_row_indices.add(actual_idx)
        self._selected_row_idx = actual_idx
        self._load_detail_panel()
        self._update_detail_panel()
        self._render_page()
        self.control.update()

    @property
    def _detail_usage_set(self) -> set[str]:
        if self._detail_panel._usage_chipset is not None:
            return self._detail_panel._usage_chipset._values
        return set()

    @property
    def _detail_value_set(self) -> set[str]:
        if self._detail_panel._value_chipset is not None:
            return self._detail_panel._value_chipset._values
        return set()

    @property
    def _batch_fields(self) -> dict:
        return self._batch_panel._field_controls

    @property
    def _batch_flag_checkboxes(self) -> dict:
        return self._batch_panel._flag_checkboxes

    def _sync_detail_panel(self) -> None:
        if self._selected_row_idx is not None and len(self._selected_row_indices) <= 1:
            self._undo_mgr.record(self._undo_mgr.take_snapshot(self._rows))
            if self._detail_panel._usage_chipset and self._detail_panel._value_chipset:
                usage = ", ".join(self._detail_panel._usage_chipset.get_values())
                value = ", ".join(self._detail_panel._value_chipset.get_values())
                self._rows[self._selected_row_idx].values["usage"] = usage
                self._rows[self._selected_row_idx].values["value"] = value
                if usage or value:
                    self._dirty = True

    def _update_detail_panel(self) -> None:
        if len(self._selected_row_indices) >= 2:
            self._batch_panel.show(
                f"Batch edit: {len(self._selected_row_indices)} rows selected",
                USAGES,
                VALUES_LIST,
                self._flag_names,
            )
            self._detail_container.content = self._batch_panel.build()
        elif len(self._selected_row_indices) == 1:
            self._detail_container.content = self._detail_panel.build()
        else:
            self._detail_container.content = self._detail_placeholder

    def _load_detail_panel(self) -> None:
        row = self._rows[self._selected_row_idx]
        self._detail_panel.show(row, USAGES, VALUES_LIST)

    def _on_batch_action(self, key: str) -> None:
        if key == "category":
            self._batch_save_category()
        elif key == "usage":
            self._batch_save_usage()
        elif key == "value":
            self._batch_save_value()
        elif key.startswith("flag:"):
            self._batch_save_flag(key[5:])
        else:
            self._batch_save_field(key)

    def _batch_save_field(self, field_key: str) -> None:
        self._undo_mgr.record(self._undo_mgr.take_snapshot(self._rows))
        self._sync_page_back()
        w = self._batch_panel._field_controls.get(field_key)
        if w is None:
            return
        value = w.value or ""
        for idx in self._selected_row_indices:
            self._rows[idx].values[field_key] = value
        self._dirty = True
        self._render_page()
        self._save_status.value = f"{field_key} applied to {len(self._selected_row_indices)} rows"
        self._save_status.color = ft.Colors.GREEN
        self.control.update()

    def _batch_save_category(self) -> None:
        self._undo_mgr.record(self._undo_mgr.take_snapshot(self._rows))
        self._sync_page_back()
        w = self._batch_panel._field_controls.get("category")
        if w is None:
            return
        value = w.value or ""
        for idx in self._selected_row_indices:
            self._rows[idx].values["category"] = value
        self._dirty = True
        self._render_page()
        self._save_status.value = f"Category applied to {len(self._selected_row_indices)} rows"
        self._save_status.color = ft.Colors.GREEN
        self.control.update()

    def _batch_save_usage(self) -> None:
        self._undo_mgr.record(self._undo_mgr.take_snapshot(self._rows))
        self._sync_page_back()
        parts = ", ".join(self._batch_panel._usage_chipset.get_values())
        for idx in self._selected_row_indices:
            self._rows[idx].values["usage"] = parts
        self._dirty = True
        self._render_page()
        self._save_status.value = f"Usage applied to {len(self._selected_row_indices)} rows"
        self._save_status.color = ft.Colors.GREEN
        self.control.update()

    def _batch_save_value(self) -> None:
        self._undo_mgr.record(self._undo_mgr.take_snapshot(self._rows))
        self._sync_page_back()
        parts = ", ".join(self._batch_panel._value_chipset.get_values())
        for idx in self._selected_row_indices:
            self._rows[idx].values["value"] = parts
        self._dirty = True
        self._render_page()
        self._save_status.value = f"Value applied to {len(self._selected_row_indices)} rows"
        self._save_status.color = ft.Colors.GREEN
        self.control.update()

    def _batch_save_flag(self, flag_name: str) -> None:
        self._undo_mgr.record(self._undo_mgr.take_snapshot(self._rows))
        self._sync_page_back()
        cb = self._batch_panel._flag_checkboxes.get(flag_name)
        if cb is None:
            return
        value = "1" if cb.value else "0"
        for idx in self._selected_row_indices:
            self._rows[idx].flags[flag_name] = value
        self._dirty = True
        self._render_page()
        self._save_status.value = f"{flag_name} applied to {len(self._selected_row_indices)} rows"
        self._save_status.color = ft.Colors.GREEN
        self.control.update()

    def _clear_selection(self) -> None:
        self._mouse_down = False
        self._detail_panel.hide()
        self._detail_container.content = self._detail_placeholder
        self._selected_row_idx = None
        self._selected_row_indices.clear()

    def _on_detail_usage_add(self, v: str) -> None:
        if self._detail_panel._usage_chipset:
            self._detail_panel._usage_chipset.add(v)

    def _detail_remove_usage(self, v: str) -> None:
        if self._detail_panel._usage_chipset:
            self._detail_panel._usage_chipset.remove(v)

    def _on_detail_value_add(self, v: str) -> None:
        if self._detail_panel._value_chipset:
            self._detail_panel._value_chipset.add(v)

    def _detail_remove_value(self, v: str) -> None:
        if self._detail_panel._value_chipset:
            self._detail_panel._value_chipset.remove(v)

    def _sync_page_back(self) -> None:
        if self._path is None or not self._dirty:
            return
        self._undo_mgr.record(self._undo_mgr.take_snapshot(self._rows))
        start = self._page_idx * PAGE_SIZE
        for i in range(len(self._body_column.controls)):
            row_idx = self._filtered[start + i] if start + i < len(self._filtered) else -1
            if row_idx < 0:
                break
            row_data = self._rows[row_idx]
            for j, fd in enumerate(self._field_defs):
                widget = self._pool_fields[i][j]
                if fd.is_flag():
                    row_data.flags[fd.key] = "1" if widget.value else "0"
                else:
                    row_data.values[fd.key] = widget.value
        self._dirty = False

    def _apply_filter(self, query: str) -> None:
        search_parts = [q.strip() for q in query.split("|") if q.strip()] if query else []
        cat_parts = [p.strip().lower() for p in self._filter_category_field.value.split("|") if p.strip()] if self._filter_category_field.value else []
        usage_parts = [p.strip().lower() for p in self._filter_usage_field.value.split("|") if p.strip()] if self._filter_usage_field.value else []
        value_parts = [p.strip().lower() for p in self._filter_value_field.value.split("|") if p.strip()] if self._filter_value_field.value else []

        self._filtered = [
            i for i, row in enumerate(self._rows)
            if (not search_parts or any(p in row.values["name"].lower() for p in search_parts))
            and (not cat_parts or any(p in row.values["category"].lower() for p in cat_parts))
            and (not usage_parts or any(p in row.values["usage"].lower() for p in usage_parts))
            and (not value_parts or any(p in row.values["value"].lower() for p in value_parts))
        ]

    def _render_page(self) -> None:
        total = len(self._filtered)
        total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
        self._page_idx = max(0, min(self._page_idx, total_pages - 1))

        start = self._page_idx * PAGE_SIZE
        end = min(start + PAGE_SIZE, total)
        count = end - start

        self._syncing = True
        for i in range(count):
            actual_idx = self._filtered[start + i]
            row_data = self._rows[actual_idx]
            self._pool_rows[i].bgcolor = ft.Colors.PRIMARY_CONTAINER if actual_idx in self._selected_row_indices else None
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
        self._syncing = False

        if self._prev_count != count:
            self._body_column.controls = self._pool_rows[:count]
            self._prev_count = count

        self._page_info.value = f"Page {self._page_idx + 1}/{total_pages}  ({total} rows)"
        self._prev_btn.disabled = self._page_idx <= 0
        self._next_btn.disabled = self._page_idx >= total_pages - 1

    def _prev_page(self, e) -> None:
        self._sync_detail_panel()
        self._sync_page_back()
        self._clear_selection()
        self._page_idx -= 1
        self._render_page()
        self.control.update()

    def _next_page(self, e) -> None:
        self._sync_detail_panel()
        self._sync_page_back()
        self._clear_selection()
        self._page_idx += 1
        self._render_page()
        self.control.update()

    def _on_search(self, e) -> None:
        self._sync_detail_panel()
        self._sync_page_back()
        query = (self._search_field.value or "").strip().lower()
        self._apply_filter(query)
        self._page_idx = 0
        self._render_page()
        self.control.update()

    def _on_search_changed(self, e) -> None:
        if self._search_task is not None and not self._search_task.done():
            self._search_task.cancel()
        self._search_task = self._page.run_task(self._debounced_search)

    def _on_filter_changed(self, e) -> None:
        if self._search_task is not None and not self._search_task.done():
            self._search_task.cancel()
        self._search_task = self._page.run_task(self._debounced_search)

    async def _debounced_search(self) -> None:
        try:
            await asyncio.sleep(0.3)
        except asyncio.CancelledError:
            return
        self._on_search(None)

    def _save(self, e) -> None:
        self._sync_detail_panel()
        self._sync_page_back()
        if self._path is None:
            return
        try:
            self.xml_repo.save(self._path, self._rows)
            self._save_status.value = "Saved"
            self._save_status.color = ft.Colors.GREEN
        except Exception as ex:
            self._save_status.value = f"Save error: {ex}"
            self._save_status.color = ft.Colors.RED

    def clear_cache(self, path: str) -> None:
        self.xml_repo.invalidate_cache(path)

    def clear(self) -> None:
        self._path = None
        self._rows = []
        self._filtered = []
        self._field_defs = []
        self._flag_names = []
        self._header_row.controls = []
        self._body_column.controls = []
        self._col_widths = []
        self._save_status.value = ""
        self._filter_category_field.value = ""
        self._filter_usage_field.value = ""
        self._filter_value_field.value = ""
        self.control.visible = False
        self._dirty = False
        self._prev_count = 0
        self._selected_row_idx = None
        self._selected_row_indices.clear()
        self._detail_panel.hide()
        self._detail_container.content = self._detail_placeholder
        self._batch_panel.hide()

        if self._tip_task is not None and not self._tip_task.done():
            self._tip_task.cancel()
        self._tip_task = None

    def _sync_widgets_to_rows(self) -> None:
        if self._path is None or not self._dirty:
            return
        start = self._page_idx * PAGE_SIZE
        for i in range(len(self._body_column.controls)):
            row_idx = self._filtered[start + i] if start + i < len(self._filtered) else -1
            if row_idx < 0:
                break
            row_data = self._rows[row_idx]
            for j, fd in enumerate(self._field_defs):
                widget = self._pool_fields[i][j]
                if fd.is_flag():
                    row_data.flags[fd.key] = "1" if widget.value else "0"
                else:
                    row_data.values[fd.key] = widget.value
        self._dirty = False

    def _on_undo(self, e):
        self._sync_widgets_to_rows()
        if self._undo_mgr.undo(self._rows):
            self._dirty = True
            self._clear_selection()
            self._render_page()
            self._refresh_button_states()
            self.control.update()

    def _on_redo(self, e):
        self._sync_widgets_to_rows()
        if self._undo_mgr.redo(self._rows):
            self._dirty = True
            self._clear_selection()
            self._render_page()
            self._refresh_button_states()
            self.control.update()

    def _refresh_button_states(self) -> None:
        self._undo_btn.disabled = not self._undo_mgr.can_undo
        self._redo_btn.disabled = not self._undo_mgr.can_redo
        self._undo_btn.update()
        self._redo_btn.update()
