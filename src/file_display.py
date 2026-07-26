from __future__ import annotations

import asyncio
import time

from lxml import etree as ET

import flet as ft

from models.field_def import FieldDef, FieldType, STATIC_FIELD_DEFS
from models.row_data import RowData


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

_cache: dict[str, list[RowData]] = {}
_cache_trees: dict[str, ET.ElementTree] = {}


def _elem_text(parent: ET.Element, tag: str, default: str = "") -> str:
    elem = parent.find(tag)
    if elem is not None and elem.text:
        return elem.text.strip()
    return default


def _set_elem_text(parent: ET.Element, tag: str, value: str) -> None:
    elem = parent.find(tag)
    if elem is not None:
        if value:
            elem.text = value
        else:
            parent.remove(elem)
    elif value:
        ET.SubElement(parent, tag).text = value


def _collect_flag_names(rows: list[RowData]) -> list[str]:
    seen: set[str] = set()
    for r in rows:
        seen.update(r.flags.keys())
    return sorted(seen)


def _names_to_str(elems: list[ET.Element]) -> str:
    names = [e.get("name", "") for e in elems if e.get("name")]
    return ", ".join(names)


def _build_row(type_elem: ET.Element) -> RowData:
    flags_elem = type_elem.find("flags")
    values: dict[str, str] = {}
    for fd in STATIC_FIELD_DEFS:
        if fd.key == "name":
            values[fd.key] = type_elem.get("name", "")
        else:
            values[fd.key] = _elem_text(type_elem, fd.key)

    cat_elem = type_elem.find("category")
    values["category"] = cat_elem.get("name", "") if cat_elem is not None else ""
    values["usage"] = _names_to_str(type_elem.findall("usage"))
    values["value"] = _names_to_str(type_elem.findall("value"))

    return RowData(
        values=values,
        flags={k: v for k, v in flags_elem.attrib.items()} if flags_elem is not None else {},
        elem=type_elem,
    )


class FileDisplay:
    def __init__(self, page: ft.Page):
        self._page = page
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
        self._detail_usage_set: set[str] = set()
        self._detail_value_set: set[str] = set()
        self._batch_panel: ft.Container | None = None
        self._batch_fields: dict[str, ft.TextField | ft.Dropdown | ft.Checkbox] = {}
        self._batch_flag_checkboxes: dict[str, ft.Checkbox] = {}
        self._batch_usage_set: set[str] = set()
        self._batch_value_set: set[str] = set()

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

        self._detail_header = ft.Text("", size=14, weight=ft.FontWeight.BOLD)
        self._batch_header = ft.Text("", size=14, weight=ft.FontWeight.BOLD)
        self._detail_usage_chips = ft.Row(wrap=True, spacing=4, run_spacing=4)
        self._detail_usage_add = ft.PopupMenuButton(
            icon=ft.Icons.ADD_CIRCLE_OUTLINED,
            tooltip="Add Usage",
            items=[
                ft.PopupMenuItem(content=ft.Text(u), on_click=lambda e, v=u: self._on_detail_usage_add(v))
                for u in USAGES
            ],
        )
        self._detail_value_chips = ft.Row(wrap=True, spacing=4, run_spacing=4)
        self._detail_value_add = ft.PopupMenuButton(
            icon=ft.Icons.ADD_CIRCLE_OUTLINED,
            tooltip="Add Value",
            items=[
                ft.PopupMenuItem(content=ft.Text(v), on_click=lambda e, v=v: self._on_detail_value_add(v))
                for v in VALUES_LIST
            ],
        )
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
        self._detail_content = ft.Column([
            self._detail_header,
            ft.Divider(height=8),
            ft.Text("Usage", size=12, weight=ft.FontWeight.BOLD),
            self._detail_usage_chips,
            self._detail_usage_add,
            ft.Divider(height=8),
            ft.Text("Value", size=12, weight=ft.FontWeight.BOLD),
            self._detail_value_chips,
            self._detail_value_add,
            ft.Divider(height=8),
            ft.Container(expand=True),
            self._tips_switcher,
        ])
        self._detail_panel = ft.Container(
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
                                self._detail_panel,
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

        if path in _cache:
            self._rows = _cache[path]
        else:
            try:
                tree = ET.parse(path)
                _cache_trees[path] = tree
                root = tree.getroot()
                self._rows = [_build_row(t) for t in root.findall("type")]
                _cache[path] = self._rows
            except Exception as ex:
                self.control.content = ft.Container(
                    content=ft.Text(f"Error parsing file: {ex}", selectable=True),
                    padding=10,
                )
                self.control.visible = True
                return

        self._flag_names = _collect_flag_names(self._rows)
        self._init_dynamic()
        self._batch_panel = None
        self._batch_fields.clear()
        self._batch_flag_checkboxes.clear()

        self._clear_selection()
        self._apply_filter("")
        self._render_page()
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

    def _sync_detail_panel(self) -> None:
        if self._selected_row_idx is not None and len(self._selected_row_indices) <= 1:
            usage = ", ".join(sorted(self._detail_usage_set))
            value = ", ".join(sorted(self._detail_value_set))
            self._rows[self._selected_row_idx].values["usage"] = usage
            self._rows[self._selected_row_idx].values["value"] = value
            if usage or value:
                self._dirty = True

    def _update_detail_panel(self) -> None:
        if len(self._selected_row_indices) >= 2:
            if self._batch_panel is None:
                self._build_batch_panel()
            self._batch_header.value = f"Batch edit: {len(self._selected_row_indices)} rows selected"
            self._detail_panel.content = self._batch_panel
        elif len(self._selected_row_indices) == 1:
            self._detail_panel.content = self._detail_content
        else:
            self._detail_panel.content = self._detail_placeholder

    def _load_detail_panel(self) -> None:
        row = self._rows[self._selected_row_idx].values
        self._detail_usage_set = {x.strip() for x in row["usage"].split(",") if x.strip()}
        self._detail_value_set = {x.strip() for x in row["value"].split(",") if x.strip()}
        self._detail_header.value = f"Selected: {row['name']}"
        self._refresh_detail_chips()
        self._detail_panel.content = self._detail_content

    def _refresh_detail_chips(self) -> None:
        self._detail_usage_chips.controls = [
            ft.Chip(label=ft.Text(s), on_delete=lambda _, v=s: self._detail_remove_usage(v))
            for s in sorted(self._detail_usage_set)
        ]
        self._detail_value_chips.controls = [
            ft.Chip(label=ft.Text(s), on_delete=lambda _, v=s: self._detail_remove_value(v))
            for s in sorted(self._detail_value_set)
        ]

    def _on_detail_usage_add(self, v: str) -> None:
        if v:
            self._detail_usage_set.add(v)
            self._refresh_detail_chips()
            self._on_field_change(None)

    def _detail_remove_usage(self, v: str) -> None:
        self._detail_usage_set.discard(v)
        self._refresh_detail_chips()
        self._on_field_change(None)

    def _on_detail_value_add(self, v: str) -> None:
        if v:
            self._detail_value_set.add(v)
            self._refresh_detail_chips()
            self._on_field_change(None)

    def _detail_remove_value(self, v: str) -> None:
        self._detail_value_set.discard(v)
        self._refresh_detail_chips()
        self._on_field_change(None)

    def _build_batch_panel(self) -> None:
        self._batch_fields = {}
        self._batch_flag_checkboxes = {}
        self._batch_usage_set = set()
        self._batch_value_set = set()
        rows = [self._batch_header, ft.Divider(height=4)]

        for fd in STATIC_FIELD_DEFS:
            if fd.key == "name":
                continue
            tf = ft.TextField(value="", dense=True, text_size=12, hint_text="", expand=True)
            self._batch_fields[fd.key] = tf
            rows.append(ft.Row([
                ft.Text(fd.label, width=70, size=12),
                tf,
                ft.IconButton(
                    icon=ft.Icons.SAVE, icon_size=18, tooltip=f"Set {fd.label}",
                    on_click=lambda e, k=fd.key: self._batch_save_field(k),
                ),
            ], spacing=4, vertical_alignment=ft.CrossAxisAlignment.CENTER))

        cat_dd = ft.Dropdown(
            value="", dense=True, text_size=12,
            expand=True,
            options=[ft.DropdownOption(key="", text="")] + [ft.DropdownOption(key=c) for c in CATEGORIES],
        )
        self._batch_fields["category"] = cat_dd
        rows.append(ft.Row([
            ft.Text("Category", width=70, size=12),
            cat_dd,
            ft.IconButton(
                icon=ft.Icons.SAVE, icon_size=18, tooltip="Set Category",
                on_click=lambda e: self._batch_save_category(),
            ),
        ], spacing=4, vertical_alignment=ft.CrossAxisAlignment.CENTER))

        rows.append(ft.Divider(height=4))

        self._batch_usage_chips = ft.Row(wrap=True, spacing=4, run_spacing=4)
        self._batch_usage_add = ft.PopupMenuButton(
            icon=ft.Icons.ADD_CIRCLE_OUTLINED,
            tooltip="Add Usage",
            items=[
                ft.PopupMenuItem(content=ft.Text(u), on_click=lambda e, v=u: self._on_batch_usage_add(v))
                for u in USAGES
            ],
        )
        rows.append(ft.Text("Usage", size=12, weight=ft.FontWeight.BOLD))
        rows.append(self._batch_usage_chips)
        rows.append(ft.Row([
            self._batch_usage_add,
            ft.IconButton(
                icon=ft.Icons.SAVE, icon_size=18, tooltip="Apply Usage",
                on_click=lambda e: self._batch_save_usage(),
            ),
        ]))

        rows.append(ft.Divider(height=4))

        self._batch_value_chips = ft.Row(wrap=True, spacing=4, run_spacing=4)
        self._batch_value_add = ft.PopupMenuButton(
            icon=ft.Icons.ADD_CIRCLE_OUTLINED,
            tooltip="Add Value",
            items=[
                ft.PopupMenuItem(content=ft.Text(v), on_click=lambda e, v=v: self._on_batch_value_add(v))
                for v in VALUES_LIST
            ],
        )
        rows.append(ft.Text("Value", size=12, weight=ft.FontWeight.BOLD))
        rows.append(self._batch_value_chips)
        rows.append(ft.Row([
            self._batch_value_add,
            ft.IconButton(
                icon=ft.Icons.SAVE, icon_size=18, tooltip="Apply Value",
                on_click=lambda e: self._batch_save_value(),
            ),
        ]))

        if self._flag_names:
            rows.append(ft.Divider(height=4))
            rows.append(ft.Text("Flags", size=12, weight=ft.FontWeight.BOLD))
            for fn in self._flag_names:
                cb = ft.Checkbox(label="", value=False)
                self._batch_flag_checkboxes[fn] = cb
                rows.append(ft.Row([
                    ft.Text(f"  {fn}", width=130, size=12),
                    cb,
                    ft.IconButton(
                        icon=ft.Icons.SAVE, icon_size=18, tooltip=f"Set {fn}",
                        on_click=lambda e, flag=fn: self._batch_save_flag(flag),
                    ),
                ], spacing=4, vertical_alignment=ft.CrossAxisAlignment.CENTER))

        rows.append(ft.Container(expand=True))
        rows.append(self._tips_switcher)

        self._batch_panel = ft.Container(
            content=ft.Column(rows, spacing=4, scroll=ft.ScrollMode.AUTO),
            padding=10,
        )

    def _batch_save_field(self, field_key: str) -> None:
        self._sync_page_back()
        w = self._batch_fields.get(field_key)
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
        self._sync_page_back()
        w = self._batch_fields.get("category")
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
        self._sync_page_back()
        parts = ", ".join(sorted(self._batch_usage_set))
        for idx in self._selected_row_indices:
            self._rows[idx].values["usage"] = parts
        self._dirty = True
        self._render_page()
        self._save_status.value = f"Usage applied to {len(self._selected_row_indices)} rows"
        self._save_status.color = ft.Colors.GREEN
        self.control.update()

    def _batch_save_value(self) -> None:
        self._sync_page_back()
        parts = ", ".join(sorted(self._batch_value_set))
        for idx in self._selected_row_indices:
            self._rows[idx].values["value"] = parts
        self._dirty = True
        self._render_page()
        self._save_status.value = f"Value applied to {len(self._selected_row_indices)} rows"
        self._save_status.color = ft.Colors.GREEN
        self.control.update()

    def _on_batch_usage_add(self, v: str) -> None:
        if v:
            self._batch_usage_set.add(v)
            self._refresh_batch_usage_chips()
            self._on_field_change(None)

    def _batch_remove_usage(self, v: str) -> None:
        self._batch_usage_set.discard(v)
        self._refresh_batch_usage_chips()
        self._on_field_change(None)

    def _on_batch_value_add(self, v: str) -> None:
        if v:
            self._batch_value_set.add(v)
            self._refresh_batch_value_chips()
            self._on_field_change(None)

    def _batch_remove_value(self, v: str) -> None:
        self._batch_value_set.discard(v)
        self._refresh_batch_value_chips()
        self._on_field_change(None)

    def _refresh_batch_usage_chips(self) -> None:
        self._batch_usage_chips.controls = [
            ft.Chip(label=ft.Text(s), on_delete=lambda _, v=s: self._batch_remove_usage(v))
            for s in sorted(self._batch_usage_set)
        ]

    def _refresh_batch_value_chips(self) -> None:
        self._batch_value_chips.controls = [
            ft.Chip(label=ft.Text(s), on_delete=lambda _, v=s: self._batch_remove_value(v))
            for s in sorted(self._batch_value_set)
        ]

    def _batch_save_flag(self, flag_name: str) -> None:
        self._sync_page_back()
        cb = self._batch_flag_checkboxes.get(flag_name)
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
        self._detail_panel.content = self._detail_placeholder
        self._selected_row_idx = None
        self._selected_row_indices.clear()
        self._detail_usage_set.clear()
        self._detail_value_set.clear()

    def _sync_page_back(self) -> None:
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
        tree = _cache_trees.get(self._path)
        if tree is None:
            return
        try:
            for row_data in self._rows:
                elem = row_data.elem
                elem.set("name", row_data.values.get("name", ""))
                _set_elem_text(elem, "nominal", row_data.values.get("nominal", ""))
                _set_elem_text(elem, "lifetime", row_data.values.get("lifetime", ""))
                _set_elem_text(elem, "restock", row_data.values.get("restock", ""))
                _set_elem_text(elem, "min", row_data.values.get("min", ""))
                _set_elem_text(elem, "quantmin", row_data.values.get("quantmin", ""))
                _set_elem_text(elem, "quantmax", row_data.values.get("quantmax", ""))
                _set_elem_text(elem, "cost", row_data.values.get("cost", ""))
                self._update_flags(elem, row_data.flags)
                self._update_single_named(elem, "category", row_data.values.get("category", ""))
                self._update_multi_named(elem, "usage", row_data.values.get("usage", ""))
                self._update_multi_named(elem, "value", row_data.values.get("value", ""))
            ET.indent(tree, space="\t")
            tree.write(self._path, encoding="UTF-8", xml_declaration=True)
            self._save_status.value = "Saved"
            self._save_status.color = ft.Colors.GREEN
        except Exception as ex:
            self._save_status.value = f"Save error: {ex}"
            self._save_status.color = ft.Colors.RED

    def _update_flags(self, parent: ET.Element, flags: dict[str, str]) -> None:
        f = parent.find("flags")
        if not flags:
            if f is not None:
                parent.remove(f)
            return
        if f is None:
            f = ET.SubElement(parent, "flags")
        f.attrib.clear()
        f.attrib.update(flags)

    def _update_single_named(self, parent: ET.Element, tag: str, name: str) -> None:
        elems = parent.findall(tag)
        existing = elems[0] if elems else None
        if name.strip():
            if existing is not None:
                existing.set("name", name.strip())
            else:
                ET.SubElement(parent, tag).set("name", name.strip())
        else:
            if existing is not None:
                parent.remove(existing)

    def _update_multi_named(self, parent: ET.Element, tag: str, s: str) -> None:
        for elem in parent.findall(tag):
            parent.remove(elem)
        for part in s.split(","):
            part = part.strip()
            if part:
                ET.SubElement(parent, tag).set("name", part)

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
        self._detail_usage_set.clear()
        self._detail_value_set.clear()
        self._detail_panel.content = self._detail_placeholder
        self._batch_panel = None
        self._batch_fields.clear()
        self._batch_flag_checkboxes.clear()
        self._batch_usage_set.clear()
        self._batch_value_set.clear()

        if self._tip_task is not None and not self._tip_task.done():
            self._tip_task.cancel()
        self._tip_task = None
