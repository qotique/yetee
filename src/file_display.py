from __future__ import annotations

import asyncio

from dataclasses import dataclass
from lxml import etree as ET

import flet as ft


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


@dataclass
class RowData:
    fields: list[str]
    flags: dict[str, str]
    elem: ET.Element


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
    cat_elem = type_elem.find("category")
    flags_elem = type_elem.find("flags")
    return RowData(
        fields=[
            type_elem.get("name", ""),
            _elem_text(type_elem, "nominal"),
            _elem_text(type_elem, "lifetime"),
            _elem_text(type_elem, "restock"),
            _elem_text(type_elem, "min"),
            _elem_text(type_elem, "quantmin"),
            _elem_text(type_elem, "quantmax"),
            _elem_text(type_elem, "cost"),
            cat_elem.get("name", "") if cat_elem is not None else "",
            _names_to_str(type_elem.findall("usage")),
            _names_to_str(type_elem.findall("value")),
        ],
        flags={k: v for k, v in flags_elem.attrib.items()} if flags_elem is not None else {},
        elem=type_elem)


_NUM_BASE_COLS = 8  # name, nominal, lifetime, restock, min, quantmin, quantmax, cost


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
        self._detail_usage_set: set[str] = set()
        self._detail_value_set: set[str] = set()

        self._flag_names: list[str] = []
        self._num_cols: int = _NUM_BASE_COLS + 1  # base + category initially
        self._pool_fields: list[list] = []
        self._pool_rows: list[ft.Container] = []

        self._save_status = ft.Text("", size=12)
        self._page_info = ft.Text("", size=12)
        self._prev_btn = ft.Button("Prev", on_click=self._prev_page)
        self._next_btn = ft.Button("Next", on_click=self._next_page)
        self._search_field = ft.TextField(
            label="Search",
            dense=True,
            text_size=12,
            width=250,
            on_submit=self._on_search,
            on_change=self._on_search_changed,
        )

        self._header_row = ft.Row(spacing=6)
        self._body_column = ft.Column(spacing=0, scroll=ft.ScrollMode.AUTO, expand=True)
        self._table_inner = ft.Column(
            [self._header_row, ft.Divider(height=1, color=ft.Colors.OUTLINE_VARIANT), self._body_column],
            spacing=0,
        )
        self._col_widths: list[int] = []

        self._detail_header = ft.Text("", size=14, weight=ft.FontWeight.BOLD)
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
            content=ft.Column(
                [
                    ft.Row(
                        [ft.Button("Save", icon=ft.Icons.SAVE, on_click=self._save), self._save_status],
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
                        ],
                        alignment=ft.MainAxisAlignment.CENTER,
                    ),
                ],
                expand=True,
            ),
        )

    def _init_dynamic(self) -> None:
        self._num_cols = _NUM_BASE_COLS + len(self._flag_names) + 1

        col_names = ["Name", "Nominal", "Lifetime", "Restock", "Min", "QuantMin", "QuantMax", "Cost"]
        for fn in self._flag_names:
            col_names.append(fn)
        col_names.append("Category")

        self._col_widths = [
            200,   # Name
            88,    # Nominal
            96,    # Lifetime
            88,    # Restock
            48,    # Min
            96,    # QuantMin
            96,    # QuantMax
            56,    # Cost
        ]
        for fn in self._flag_names:
            self._col_widths.append(max(60, len(fn) * 8 + 24))
        self._col_widths.append(150)  # Category
        table_width = sum(self._col_widths) + (self._num_cols - 1) * 6

        align_left = ft.TextAlign.LEFT
        align_right = ft.TextAlign.RIGHT
        self._align = [align_left] + [align_right] * 7 + [align_left] * len(self._flag_names) + [align_left]

        flag_offset = _NUM_BASE_COLS
        cat_idx = flag_offset + len(self._flag_names)

        header_cells = []
        for ci in range(self._num_cols):
            text_align = self._align[ci]
            cell_align = ft.Alignment.CENTER_LEFT if text_align == align_left else ft.Alignment.CENTER_RIGHT
            hc = ft.Container(
                content=ft.Text(col_names[ci], size=12, weight=ft.FontWeight.BOLD, text_align=text_align),
                width=self._col_widths[ci],
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
            for ci in range(self._num_cols):
                if ci == cat_idx:
                    w = ft.Dropdown(
                        value="",
                        dense=True,
                        text_size=12,
                        height=36,
                        content_padding=ft.Padding(left=12, top=2, right=12, bottom=2),
                        border_color=ft.Colors.with_opacity(0.5, ft.Colors.OUTLINE),
                        focused_border_color=ft.Colors.PRIMARY,
                        filled=False,
                        options=[ft.DropdownOption(key="", text="")] + [ft.DropdownOption(key=c) for c in CATEGORIES],
                        on_select=self._on_field_change,
                        hover_color=ft.Colors.TRANSPARENT,
                        on_focus=lambda e, idx=ri: self._on_row_click(idx),
                        expand=True,
                    )
                elif ci >= flag_offset and ci < cat_idx:
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
                        text_align=self._align[ci],
                        min_lines=1,
                        max_lines=1,
                        on_change=self._on_field_change,
                        hover_color=ft.Colors.TRANSPARENT,
                        filled=False,
                        on_focus=lambda e, idx=ri: self._on_row_click(idx),
                        expand=True,
                    )
                fields.append(w)
                if flag_offset <= ci < cat_idx:
                    cell = ft.Container(
                        content=ft.Row(
                            [w],
                            alignment=ft.MainAxisAlignment.CENTER,
                        ),
                        width=self._col_widths[ci],
                        alignment=ft.Alignment.CENTER,
                    )
                else:
                    cell = ft.Container(
                        content=w,
                        width=self._col_widths[ci],
                    )
                row_cells.append(cell)
            self._pool_fields.append(fields)
            self._pool_rows.append(ft.Container(
                content=ft.Row(row_cells, spacing=6),
                bgcolor=None,
                border=ft.border.Border(
                    bottom=ft.border.BorderSide(1, ft.Colors.with_opacity(0.12, ft.Colors.OUTLINE_VARIANT)),
                ),
            ))

    def load_file(self, path: str) -> None:
        self._path = path
        self._save_status.value = ""
        self._page_idx = 0
        self._search_field.value = ""
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

    def _on_row_click(self, pool_slot: int) -> None:
        start = self._page_idx * PAGE_SIZE
        actual_idx = self._filtered[start + pool_slot] if start + pool_slot < len(self._filtered) else -1
        if actual_idx < 0 or actual_idx == self._selected_row_idx:
            return
        self._sync_page_back()
        self._sync_detail_panel()
        self._selected_row_idx = actual_idx
        self._load_detail_panel()
        self._render_page()
        self.control.update()

    def _sync_detail_panel(self) -> None:
        if self._selected_row_idx is not None:
            usage = ", ".join(sorted(self._detail_usage_set))
            value = ", ".join(sorted(self._detail_value_set))
            self._rows[self._selected_row_idx].fields[9] = usage
            self._rows[self._selected_row_idx].fields[10] = value
            if usage or value:
                self._dirty = True

    def _load_detail_panel(self) -> None:
        row = self._rows[self._selected_row_idx].fields
        self._detail_usage_set = {x.strip() for x in row[9].split(",") if x.strip()}
        self._detail_value_set = {x.strip() for x in row[10].split(",") if x.strip()}
        self._detail_header.value = f"Selected: {row[0]}"
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

    def _clear_selection(self) -> None:
        self._detail_panel.content = self._detail_placeholder
        self._selected_row_idx = None
        self._detail_usage_set.clear()
        self._detail_value_set.clear()

    def _sync_page_back(self) -> None:
        if self._path is None or not self._dirty:
            return
        start = self._page_idx * PAGE_SIZE
        flag_offset = _NUM_BASE_COLS
        for i in range(len(self._body_column.controls)):
            row_idx = self._filtered[start + i] if start + i < len(self._filtered) else -1
            if row_idx < 0:
                break
            row_data = self._rows[row_idx]
            for j in range(self._num_cols):
                widget = self._pool_fields[i][j]
                if flag_offset <= j < flag_offset + len(self._flag_names):
                    flag_name = self._flag_names[j - flag_offset]
                    row_data.flags[flag_name] = "1" if widget.value else "0"
                elif j < flag_offset:
                    row_data.fields[j] = widget.value
                else:
                    row_data.fields[_NUM_BASE_COLS] = widget.value
        self._dirty = False

    def _apply_filter(self, query: str) -> None:
        if not query:
            self._filtered = list(range(len(self._rows)))
        else:
            self._filtered = [
                i for i, row in enumerate(self._rows)
                if query in row.fields[0].lower()
            ]

    def _render_page(self) -> None:
        total = len(self._filtered)
        total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
        self._page_idx = max(0, min(self._page_idx, total_pages - 1))

        start = self._page_idx * PAGE_SIZE
        end = min(start + PAGE_SIZE, total)
        count = end - start

        flag_offset = _NUM_BASE_COLS
        self._syncing = True
        for i in range(count):
            actual_idx = self._filtered[start + i]
            row_data = self._rows[actual_idx]
            row = row_data.fields
            self._pool_rows[i].bgcolor = ft.Colors.PRIMARY_CONTAINER if actual_idx == self._selected_row_idx else None
            for j in range(self._num_cols):
                field = self._pool_fields[i][j]
                if flag_offset <= j < flag_offset + len(self._flag_names):
                    flag_name = self._flag_names[j - flag_offset]
                    val = row_data.flags.get(flag_name, "0") == "1"
                    if field.value != val:
                        field.value = val
                elif j < flag_offset:
                    if field.value != row[j]:
                        field.value = row[j]
                else:
                    if field.value != row[_NUM_BASE_COLS]:
                        field.value = row[_NUM_BASE_COLS]
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
        self._clear_selection()
        query = (self._search_field.value or "").strip().lower()
        self._apply_filter(query)
        self._page_idx = 0
        self._render_page()
        self.control.update()

    def _on_search_changed(self, e) -> None:
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
            root = tree.getroot()
            for row_data in self._rows:
                row = row_data.fields
                elem = row_data.elem
                elem.set("name", row[0])
                _set_elem_text(elem, "nominal", row[1])
                _set_elem_text(elem, "lifetime", row[2])
                _set_elem_text(elem, "restock", row[3])
                _set_elem_text(elem, "min", row[4])
                _set_elem_text(elem, "quantmin", row[5])
                _set_elem_text(elem, "quantmax", row[6])
                _set_elem_text(elem, "cost", row[7])
                self._update_flags(elem, row_data.flags)
                self._update_single_named(elem, "category", row[_NUM_BASE_COLS])
                self._update_multi_named(elem, "usage", row[9])
                self._update_multi_named(elem, "value", row[10])
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
        self._flag_names = []
        self._num_cols = _NUM_BASE_COLS + 1
        self._header_row.controls = []
        self._body_column.controls = []
        self._col_widths = []
        self._save_status.value = ""
        self.control.visible = False
        self._dirty = False
        self._prev_count = 0
        self._selected_row_idx = None
        self._detail_usage_set.clear()
        self._detail_value_set.clear()
        self._detail_panel.content = self._detail_placeholder

        if self._tip_task is not None and not self._tip_task.done():
            self._tip_task.cancel()
        self._tip_task = None
