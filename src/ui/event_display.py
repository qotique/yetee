from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable

from lxml import etree as ET

import flet as ft

from commands.registry import CommandRegistry
from controllers.dirty_state_manager import DirtyStateManager
from controllers.pagination_controller import PaginationController
from controllers.search_controller import SearchController
from controllers.table_controller import TableController
from models.field_def import FieldDef, FieldType
from models.row_data import RowData
from models.undo_manager import UndoManager
from repository.event_repository import (
    EventRepository,
    EVENT_FLAG_NAMES,
)
from repository.file_cache import FileCache
from services.entertainment_service import EntertainmentService

logger = logging.getLogger(__name__)

EVENT_FIELD_DEFS: list[FieldDef] = [
    FieldDef(
        "name",
        "Name",
        FieldType.TEXT,
        width=180,
    ),
    FieldDef(
        "nominal",
        "Nominal",
        FieldType.TEXT,
        width=88,
        align=ft.TextAlign.RIGHT,
    ),
    FieldDef(
        "min",
        "Min",
        FieldType.TEXT,
        width=48,
        align=ft.TextAlign.RIGHT,
    ),
    FieldDef(
        "max",
        "Max",
        FieldType.TEXT,
        width=48,
        align=ft.TextAlign.RIGHT,
    ),
    FieldDef(
        "lifetime",
        "Lifetime",
        FieldType.TEXT,
        width=88,
        align=ft.TextAlign.RIGHT,
    ),
    FieldDef(
        "restock",
        "Restock",
        FieldType.TEXT,
        width=88,
        align=ft.TextAlign.RIGHT,
    ),
    FieldDef(
        "saferadius",
        "SafeR",
        FieldType.TEXT,
        width=72,
        align=ft.TextAlign.RIGHT,
    ),
    FieldDef(
        "distanceradius",
        "DistR",
        FieldType.TEXT,
        width=72,
        align=ft.TextAlign.RIGHT,
    ),
    FieldDef(
        "cleanupradius",
        "CleanR",
        FieldType.TEXT,
        width=72,
        align=ft.TextAlign.RIGHT,
    ),
    FieldDef(
        "active",
        "Active",
        FieldType.TEXT,
        width=64,
        align=ft.TextAlign.RIGHT,
    ),
    FieldDef(
        "position",
        "Position",
        FieldType.SINGLE_NAMED,
        width=110,
        options=["fixed", "player"],
    ),
    FieldDef(
        "limit",
        "Limit",
        FieldType.SINGLE_NAMED,
        width=110,
        options=["mixed", "child", "parent"],
    ),
]

EVENT_PAGE_SIZE = 50

_SPAWN_COL_WIDTHS: dict[str, int] = {
    "x": 80,
    "z": 80,
    "y": 80,
    "a": 80,
    "group": 180,
}


class EventDisplay:
    on_saved: Callable[[], None] | None = None

    def __init__(
        self,
        page: ft.Page,
        event_repo: EventRepository | None = None,
        cache: FileCache | None = None,
        entertainment_service: EntertainmentService | None = None,
        commands: CommandRegistry | None = None,
    ):
        self._page = page
        self._cache = cache or FileCache()
        self._event_repo = event_repo or EventRepository(cache=self._cache)
        self._entertainment_service = entertainment_service
        self._commands = commands

        self._undo_mgr = UndoManager()
        self._table_ctrl = TableController(page)
        self._pagination = PaginationController(EVENT_PAGE_SIZE)
        self._search = SearchController()
        self._dirty_state = DirtyStateManager()

        self._events_path: str | None = None
        self._spawns_path: str | None = None
        self._spawns_data: dict[str, dict] = {}
        self._all_spawn_keys: list[str] = ["x", "z", "y", "a"]
        self._rows: list[RowData] = []
        self._filtered: list[int] = []

        self._selected_row_idx: int | None = None
        self._selected_row_indices: set[int] = set()
        self._shift_pressed: bool = False

        self._search_task: asyncio.Task | None = None

        self._detail_row_key: str | None = None
        self._detail_child_rows: list[list[ft.Control]] = []
        self._detail_child_column: ft.Column | None = None
        self._detail_spawn_keys: list[str] = []
        self._detail_spawn_widths: dict[str, int] = {}
        self._detail_spawn_rows: list[
            tuple[dict[str, ft.TextField], ft.IconButton]
        ] = []
        self._detail_spawn_column: ft.Column | None = None
        self._detail_zone_fields: dict[str, ft.TextField] = {}

        self._table_ctrl.set_callbacks(
            on_row_click=self._on_row_click,
            on_field_change=self._on_field_change,
        )

        self._save_text = ft.Text("", size=12, selectable=True)
        self._save_status = ft.Row(
            controls=[self._save_text],
            height=48,
            width=36 * 6,
            wrap=True,
            auto_scroll=True,
            scroll=ft.ScrollMode.HIDDEN,
        )
        self._page_info = ft.Text("", size=12)
        self._prev_btn = ft.Button(
            "Prev", on_click=self._bind("prev_page", self._prev_page)
        )
        self._next_btn = ft.Button(
            "Next", on_click=self._bind("next_page", self._next_page)
        )
        self._save_btn = ft.Button(
            "Save", icon=ft.Icons.SAVE, on_click=self._bind("save", self.save_current)
        )
        self._undo_btn = ft.IconButton(
            icon=ft.Icons.UNDO, on_click=self._bind("undo", self._on_undo)
        )
        self._redo_btn = ft.IconButton(
            icon=ft.Icons.REDO, on_click=self._bind("redo", self._on_redo)
        )

        self._search_field = ft.TextField(
            label="Search",
            icon=ft.Icons.SEARCH,
            dense=True,
            text_size=12,
            width=250,
            on_submit=self._on_search,
            on_change=self._on_search_changed,
            autofocus=True,
        )

        self._fab = ft.FloatingActionButton(
            icon=ft.Icons.ADD,
            on_click=self._on_fab_click,
        )

        self._detail_container = ft.Container(
            width=580,
            padding=10,
            content=self._build_placeholder(),
        )

        self.button_row = ft.Row(
            [
                self._save_btn,
                self._undo_btn,
                self._redo_btn,
                self._save_status,
            ],
            alignment=ft.MainAxisAlignment.START,
        )

        self._keyboard_listener = ft.KeyboardListener(
            autofocus=True,
            on_key_down=self._on_key_down,
            on_key_up=self._on_key_up,
            content=ft.Column(
                [
                    ft.Row(
                        [
                            ft.Stack(
                                [
                                    ft.Container(
                                        content=ft.Column(
                                            [
                                                ft.Row(
                                                    [
                                                        self._table_ctrl.get_table_widget()
                                                    ],
                                                    scroll=ft.ScrollMode.ALWAYS,
                                                    expand=True,
                                                    vertical_alignment=ft.CrossAxisAlignment.STRETCH,
                                                ),
                                            ],
                                            expand=True,
                                            spacing=0,
                                        ),
                                        border=ft.border.Border(
                                            ft.border.BorderSide(
                                                1, ft.Colors.OUTLINE_VARIANT
                                            ),
                                            ft.border.BorderSide(
                                                1, ft.Colors.OUTLINE_VARIANT
                                            ),
                                            ft.border.BorderSide(
                                                1, ft.Colors.OUTLINE_VARIANT
                                            ),
                                            ft.border.BorderSide(
                                                1, ft.Colors.OUTLINE_VARIANT
                                            ),
                                        ),
                                        border_radius=8,
                                        expand=True,
                                    ),
                                    ft.Container(
                                        content=self._fab,
                                        right=16,
                                        bottom=16,
                                    ),
                                ],
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
                        ],
                        alignment=ft.MainAxisAlignment.CENTER,
                    ),
                ],
                expand=True,
            ),
        )
        self.control = ft.Container(
            visible=False,
            expand=True,
            content=self._keyboard_listener,
        )

        logger.debug("EventDisplay initialized")

    def _bind(
        self,
        command_id: str,
        fallback: Callable[[object], None],
    ) -> Callable[[object], None]:
        commands = self._commands
        if commands is not None:
            return lambda _e: commands.invoke(command_id)
        return fallback

    def _execute_command(self, command_id: str, fallback: Callable[[], None]) -> None:
        if self._commands is not None:
            self._commands.invoke(command_id)
        else:
            fallback()

    def _refresh_commands(self) -> None:
        if self._commands is not None:
            self._commands.refresh()

    @property
    def _dirty(self) -> bool:
        return self._dirty_state.is_dirty

    @_dirty.setter
    def _dirty(self, value: bool) -> None:
        if value:
            self._dirty_state.mark_dirty()
        else:
            self._dirty_state.mark_clean()

    @property
    def _page_idx(self) -> int:
        return self._pagination.page_index

    def _build_placeholder(self) -> ft.Container:
        return ft.Container(
            content=ft.Column(
                [
                    ft.Text(
                        "Select event",
                        size=16,
                        italic=True,
                        color=ft.Colors.GREY,
                        text_align=ft.TextAlign.CENTER,
                    ),
                    ft.Container(expand=True),
                ]
            ),
            alignment=ft.Alignment.CENTER,
            expand=True,
        )

    def _init_table(self) -> None:
        all_defs = list(EVENT_FIELD_DEFS)
        for fn in EVENT_FLAG_NAMES:
            width = max(60, len(fn) * 8 + 24)
            all_defs.append(FieldDef(fn, fn, FieldType.FLAG, width=width))

        self._table_ctrl.field_defs.clear()
        self._table_ctrl.field_defs.extend(all_defs)
        self._table_ctrl.flag_names = list(EVENT_FLAG_NAMES)

        col_widths = [fd.width for fd in all_defs]
        table_width = sum(col_widths) + (len(all_defs) - 1) * 6

        align_right = ft.TextAlign.RIGHT
        header_cells = []
        for fd in all_defs:
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
            )
            header_cells.append(hc)
        self._table_ctrl._header_row.controls = header_cells
        header = self._table_ctrl._header_row
        if hasattr(header, "_table_inner"):
            header._table_inner.width = table_width

        self._table_ctrl._pool_fields = []
        self._table_ctrl._pool_rows = []

        for ri in range(EVENT_PAGE_SIZE):
            fields: list[ft.Control] = []
            row_cells: list[ft.Container] = []
            for ci, fd in enumerate(all_defs):
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

            self._table_ctrl._pool_fields.append(fields)
            self._table_ctrl._pool_rows.append(
                ft.Container(
                    content=ft.Row(row_cells, spacing=6),
                    bgcolor=None,
                    border=ft.border.Border(
                        bottom=ft.border.BorderSide(
                            1, ft.Colors.with_opacity(0.12, ft.Colors.OUTLINE_VARIANT)
                        ),
                    ),
                    on_click=lambda e, idx=ri: self._trigger_row_click(idx),
                )
            )

        logger.debug(
            "Event table pool initialized: %d rows x %d cols",
            EVENT_PAGE_SIZE,
            len(all_defs),
        )

    def _trigger_row_click(self, pool_slot: int) -> None:
        self._on_row_click(pool_slot)

    def load_file(self, events_path: str, spawns_path: str | None = None) -> None:
        self._events_path = events_path
        self._spawns_path = spawns_path
        self._save_text.value = ""
        self._pagination.reset()
        self._search.reset()
        self._search_field.value = ""
        self._dirty_state.reset()
        self._undo_mgr.clear()

        try:
            self._rows = self._event_repo.parse_file(events_path)
        except Exception as ex:
            logger.error("Error loading events %s: %s", events_path, ex)
            self.control.content = ft.Container(
                content=ft.Text(f"Error parsing events: {ex}", selectable=True),
                padding=10,
            )
            self.control.visible = True
            return

        if spawns_path:
            self._spawns_data = self._event_repo.parse_spawns(spawns_path)
        else:
            self._spawns_data = {}

        self._compute_all_spawn_keys()
        self._init_table()
        self._clear_selection()
        self._apply_filter("")
        self._render_page()
        self._refresh_button_states()
        self.control.visible = True
        try:
            self.control.update()
        except RuntimeError:
            pass
        self._page.run_task(self._keyboard_listener.focus)
        logger.info("Loaded events: %s (%d events)", events_path, len(self._rows))

    def _compute_all_spawn_keys(self) -> None:
        base = ["x", "z", "y", "a"]
        extras: set[str] = set()
        for info in self._spawns_data.values():
            if isinstance(info, dict):
                for pos in info.get("positions", []):
                    extras.update(k for k in pos.keys() if k not in base)
        self._all_spawn_keys = base + sorted(extras)

    def save_current(self, e: object) -> None:
        self._sync_page_back()
        if self._events_path is None:
            return
        try:
            self._event_repo.save(self._events_path, self._rows)
            if self._spawns_path and self._spawns_data:
                self._event_repo.save_spawns(self._spawns_path, self._spawns_data)
            self._save_text.value = "Saved"
            self._save_text.color = ft.Colors.GREEN
            self._dirty_state.mark_clean()
            logger.info("Saved events %s", self._events_path)
            if self.on_saved:
                self.on_saved()
        except Exception as ex:
            self._save_text.value = f"Save error: {ex}"
            self._save_text.color = ft.Colors.RED
            logger.error("Save failed for %s: %s", self._events_path, ex)

    def _on_field_change(self, e: object) -> None:
        if not self._dirty_state.is_dirty or not self._undo_mgr.can_undo:
            self._undo_mgr.record(self._undo_mgr.take_snapshot(self._rows))
            self._refresh_button_states()
        self._dirty_state.mark_dirty()

    def _on_fab_click(self, e: object) -> None:
        if self._events_path is None:
            return
        if self._shift_pressed:
            self._execute_command("delete_row", self._delete_selected)
        else:
            self._execute_command("add_row", self._add_event)

    def _add_event(self) -> None:
        if self._events_path is None:
            return
        tree = self._cache.get_tree(self._events_path)
        if tree is None:
            return
        root = tree.getroot()

        new_elem = ET.SubElement(root, "event")
        new_elem.set("name", "")
        ET.SubElement(new_elem, "nominal").text = "0"
        ET.SubElement(new_elem, "min").text = "0"
        ET.SubElement(new_elem, "max").text = "0"
        ET.SubElement(new_elem, "lifetime").text = "0"
        ET.SubElement(new_elem, "restock").text = "0"
        ET.SubElement(new_elem, "saferadius").text = "0"
        ET.SubElement(new_elem, "distanceradius").text = "0"
        ET.SubElement(new_elem, "cleanupradius").text = "0"
        ET.SubElement(new_elem, "position").text = "fixed"
        ET.SubElement(new_elem, "limit").text = "mixed"
        ET.SubElement(new_elem, "active").text = "1"
        flags_elem = ET.SubElement(new_elem, "flags")
        for fn in EVENT_FLAG_NAMES:
            flags_elem.set(fn, "0")
        ET.SubElement(new_elem, "children")

        new_row = RowData(
            values={fd.key: "" for fd in EVENT_FIELD_DEFS},
            flags={fn: "0" for fn in EVENT_FLAG_NAMES},
            elem=new_elem,
        )
        new_row.values["name"] = ""
        new_row.values["nominal"] = "0"
        new_row.values["min"] = "0"
        new_row.values["max"] = "0"
        new_row.values["lifetime"] = "0"
        new_row.values["restock"] = "0"
        new_row.values["saferadius"] = "0"
        new_row.values["distanceradius"] = "0"
        new_row.values["cleanupradius"] = "0"
        new_row.values["position"] = "fixed"
        new_row.values["limit"] = "mixed"
        new_row.values["active"] = "1"

        self._undo_mgr.record(self._undo_mgr.take_snapshot(self._rows))
        self._rows.insert(0, new_row)
        self._apply_filter(self._search_field.value or "")
        self._selected_row_idx = 0
        self._selected_row_indices = {0}
        self._pagination.reset()
        self._dirty_state.mark_dirty()
        self._render_page()
        self.control.update()

    def _delete_selected(self) -> None:
        if not self._selected_row_indices:
            return
        self._sync_page_back()
        tree = self._cache.get_tree(self._events_path)
        if tree is None:
            return
        root = tree.getroot()

        self._undo_mgr.record(self._undo_mgr.take_snapshot(self._rows))
        for idx in sorted(self._selected_row_indices, reverse=True):
            row = self._rows[idx]
            if row.elem is not None:
                root.remove(row.elem)
            del self._rows[idx]

        self._clear_selection()
        self._apply_filter(self._search_field.value or "")
        self._pagination.clamp(len(self._filtered))
        self._dirty_state.mark_dirty()
        self._render_page()
        self.control.update()

    def _on_key_down(self, e: ft.KeyDownEvent) -> None:
        if "shift" in e.key.lower():
            self._shift_pressed = True
            self._update_fab_icon()

    def _on_key_up(self, e: ft.KeyUpEvent) -> None:
        if "shift" in e.key.lower():
            self._shift_pressed = False
            self._update_fab_icon()

    def _update_fab_icon(self) -> None:
        is_cat = self._entertainment_service and self._entertainment_service.cat_mode
        if is_cat:
            self._fab.icon = ft.Icons.PETS
        elif self._shift_pressed:
            self._fab.icon = ft.Icons.DELETE
        else:
            self._fab.icon = ft.Icons.ADD
        try:
            self._fab.update()
        except RuntimeError:
            pass

    def update_cat_icons(self) -> None:
        is_cat = self._entertainment_service and self._entertainment_service.cat_mode
        self._save_btn.icon = ft.Icons.PETS if is_cat else ft.Icons.SAVE
        self._undo_btn.icon = ft.Icons.PETS if is_cat else ft.Icons.UNDO
        self._redo_btn.icon = ft.Icons.PETS if is_cat else ft.Icons.REDO
        self._search_field.icon = ft.Icons.PETS if is_cat else ft.Icons.SEARCH
        for ctrl in (
            self._save_btn,
            self._undo_btn,
            self._redo_btn,
            self._search_field,
        ):
            try:
                ctrl.update()
            except RuntimeError:
                pass
        self._update_fab_icon()
        if self._selected_row_idx is not None:
            self._update_detail_panel()

    def _on_row_click(self, pool_slot: int) -> None:
        start = self._pagination.page_index * EVENT_PAGE_SIZE
        actual_idx = (
            self._filtered[start + pool_slot]
            if start + pool_slot < len(self._filtered)
            else -1
        )
        if actual_idx < 0:
            return
        self._sync_page_back()
        self._selected_row_indices = {actual_idx}
        self._selected_row_idx = actual_idx
        self._update_detail_panel()
        self._render_page()
        self.control.update()
        self._refresh_commands()

    def _update_detail_panel(self) -> None:
        self._detail_row_key = None
        self._detail_child_rows = []
        self._detail_child_column = None
        self._detail_spawn_keys = []
        self._detail_spawn_widths = {}
        self._detail_spawn_rows = []
        self._detail_spawn_column = None
        self._detail_zone_fields = {}
        if self._selected_row_idx is None:
            self._detail_container.content = self._build_placeholder()
        else:
            row = self._rows[self._selected_row_idx]
            self._detail_container.content = self._build_event_detail(row)
        self._detail_container.update()

    def _build_event_detail(self, row: RowData) -> ft.Container:
        name = row.values.get("name", "(unnamed)")
        self._detail_row_key = name
        self._detail_child_rows = []
        self._detail_spawn_rows = []
        self._detail_zone_fields = {}

        children = self._event_repo.get_children(row)
        spawn_info = self._spawns_data.get(name, {})
        if isinstance(spawn_info, dict):
            positions = spawn_info.get("positions", [])
            zone = spawn_info.get("zone", {})
        else:
            positions = []
            zone = {}

        detail_items: list[ft.Control] = [
            ft.Text(name, size=16, weight=ft.FontWeight.BOLD),
            ft.Divider(height=8),
            ft.Text("Children:", weight=ft.FontWeight.BOLD, size=13),
        ]

        child_header = ft.Row(
            [
                ft.Text("Type", size=11, weight=ft.FontWeight.BOLD, width=200),
                ft.Text(
                    "Min",
                    size=11,
                    weight=ft.FontWeight.BOLD,
                    width=55,
                    text_align=ft.TextAlign.RIGHT,
                ),
                ft.Text(
                    "Max",
                    size=11,
                    weight=ft.FontWeight.BOLD,
                    width=55,
                    text_align=ft.TextAlign.RIGHT,
                ),
                ft.Text(
                    "LootMin",
                    size=11,
                    weight=ft.FontWeight.BOLD,
                    width=70,
                    text_align=ft.TextAlign.RIGHT,
                ),
                ft.Text(
                    "LootMax",
                    size=11,
                    weight=ft.FontWeight.BOLD,
                    width=70,
                    text_align=ft.TextAlign.RIGHT,
                ),
                ft.Container(width=32),
            ],
            spacing=2,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )
        detail_items.append(child_header)

        self._detail_child_column = ft.Column(spacing=2)
        for idx, c in enumerate(children):
            row_ctrls = self._make_child_row(c, idx)
            self._detail_child_rows.append(row_ctrls)
            self._detail_child_column.controls.append(
                ft.Row(
                    row_ctrls,
                    spacing=2,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                )
            )
        is_cat = self._entertainment_service and self._entertainment_service.cat_mode
        add_child_btn = ft.IconButton(
            icon=ft.Icons.PETS if is_cat else ft.Icons.ADD_CIRCLE_OUTLINE,
            icon_size=18,
            tooltip="Add child",
            on_click=self._on_add_child,
        )
        self._detail_child_column.controls.append(
            ft.Row([add_child_btn], alignment=ft.MainAxisAlignment.START)
        )
        detail_items.append(self._detail_child_column)

        detail_items.append(ft.Divider(height=8))
        detail_items.append(ft.Text("Zone:", weight=ft.FontWeight.BOLD, size=13))

        zone_header = ft.Row(spacing=4, vertical_alignment=ft.CrossAxisAlignment.CENTER)
        for zk in ("smin", "smax", "dmin", "dmax", "r"):
            zone_header.controls.append(
                ft.Text(
                    zk.upper(),
                    size=11,
                    weight=ft.FontWeight.BOLD,
                    width=70,
                    text_align=ft.TextAlign.CENTER,
                )
            )
        detail_items.append(zone_header)
        zone_row = ft.Row(spacing=4, vertical_alignment=ft.CrossAxisAlignment.CENTER)
        for zk in ("smin", "smax", "dmin", "dmax", "r"):
            fld = ft.TextField(
                value=zone.get(zk, ""),
                dense=True,
                text_size=11,
                width=70,
                on_change=self._on_field_change,
            )
            self._detail_zone_fields[zk] = fld
            zone_row.controls.append(fld)
        detail_items.append(zone_row)

        detail_items.append(ft.Divider(height=8))
        detail_items.append(
            ft.Text("Spawn positions:", weight=ft.FontWeight.BOLD, size=13)
        )

        self._detail_spawn_keys = self._all_spawn_keys

        self._detail_spawn_widths = {
            k: _SPAWN_COL_WIDTHS.get(k, 100) for k in self._detail_spawn_keys
        }

        self._detail_spawn_column = ft.Column(spacing=2)
        pos_header = ft.Row(spacing=2, vertical_alignment=ft.CrossAxisAlignment.CENTER)
        for k in self._detail_spawn_keys:
            pos_header.controls.append(
                ft.Text(
                    k.upper(),
                    size=11,
                    weight=ft.FontWeight.BOLD,
                    width=self._detail_spawn_widths[k],
                )
            )
        pos_header.controls.append(ft.Container(width=32))
        self._detail_spawn_column.controls.append(pos_header)
        for idx, p in enumerate(positions):
            fields, delete_btn = self._make_spawn_row(p, idx)
            self._detail_spawn_rows.append((fields, delete_btn))
            self._detail_spawn_column.controls.append(
                ft.Row(
                    list(fields.values()) + [delete_btn],
                    spacing=2,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                )
            )
        is_cat = self._entertainment_service and self._entertainment_service.cat_mode
        add_spawn_btn = ft.IconButton(
            icon=ft.Icons.PETS if is_cat else ft.Icons.ADD_CIRCLE_OUTLINE,
            icon_size=18,
            tooltip="Add spawn position",
            on_click=self._on_add_spawn,
        )
        self._detail_spawn_column.controls.append(
            ft.Row([add_spawn_btn], alignment=ft.MainAxisAlignment.START)
        )
        detail_items.append(
            ft.Row([self._detail_spawn_column], scroll=ft.ScrollMode.ALWAYS)
        )

        return ft.Container(
            content=ft.Column(detail_items, scroll=ft.ScrollMode.AUTO, expand=True),
            expand=True,
        )

    def _make_child_row(self, attrs: dict[str, str], idx: int) -> list[ft.Control]:
        type_fld = ft.TextField(
            value=attrs.get("type", ""),
            dense=True,
            text_size=11,
            width=200,
            on_change=self._on_field_change,
        )
        min_fld = ft.TextField(
            value=attrs.get("min", ""),
            dense=True,
            text_size=11,
            width=55,
            text_align=ft.TextAlign.RIGHT,
            on_change=self._on_field_change,
        )
        max_fld = ft.TextField(
            value=attrs.get("max", ""),
            dense=True,
            text_size=11,
            width=55,
            text_align=ft.TextAlign.RIGHT,
            on_change=self._on_field_change,
        )
        lootmin_fld = ft.TextField(
            value=attrs.get("lootmin", ""),
            dense=True,
            text_size=11,
            width=70,
            text_align=ft.TextAlign.RIGHT,
            on_change=self._on_field_change,
        )
        lootmax_fld = ft.TextField(
            value=attrs.get("lootmax", ""),
            dense=True,
            text_size=11,
            width=70,
            text_align=ft.TextAlign.RIGHT,
            on_change=self._on_field_change,
        )
        is_cat = self._entertainment_service and self._entertainment_service.cat_mode
        delete_btn = ft.IconButton(
            icon=ft.Icons.PETS if is_cat else ft.Icons.DELETE_OUTLINE,
            icon_size=16,
            tooltip="Delete child",
            on_click=lambda e, i=idx: self._delete_child(i),
        )
        return [type_fld, min_fld, max_fld, lootmin_fld, lootmax_fld, delete_btn]

    def _make_spawn_row(
        self, attrs: dict[str, str], idx: int
    ) -> tuple[dict[str, ft.TextField], ft.IconButton]:
        fields: dict[str, ft.TextField] = {}
        for k in self._detail_spawn_keys:
            fields[k] = ft.TextField(
                value=attrs.get(k, ""),
                dense=True,
                text_size=10,
                width=self._detail_spawn_widths.get(k, 70),
                on_change=self._on_field_change,
            )
        is_cat = self._entertainment_service and self._entertainment_service.cat_mode
        delete_btn = ft.IconButton(
            icon=ft.Icons.PETS if is_cat else ft.Icons.DELETE_OUTLINE,
            icon_size=16,
            tooltip="Delete spawn",
            on_click=lambda e, i=idx: self._delete_spawn(i),
        )
        return fields, delete_btn

    def _on_add_child(self, e: object) -> None:
        if self._detail_child_column is None:
            return
        idx = len(self._detail_child_rows)
        row_ctrls = self._make_child_row({}, idx)
        self._detail_child_rows.append(row_ctrls)
        add_btn_idx = len(self._detail_child_column.controls) - 1
        self._detail_child_column.controls.insert(
            add_btn_idx,
            ft.Row(
                row_ctrls, spacing=2, vertical_alignment=ft.CrossAxisAlignment.CENTER
            ),
        )
        self._detail_child_column.update()
        self._dirty_state.mark_dirty()
        self._refresh_button_states()

    def _delete_child(self, idx: int) -> None:
        if (
            idx < 0
            or idx >= len(self._detail_child_rows)
            or self._detail_child_column is None
        ):
            return
        del self._detail_child_rows[idx]
        del self._detail_child_column.controls[idx]
        self._detail_child_column.update()
        self._dirty_state.mark_dirty()
        self._refresh_button_states()
        for i in range(idx, len(self._detail_child_rows)):
            delete_btn = self._detail_child_rows[i][-1]
            delete_btn.on_click = lambda e, new_i=i: self._delete_child(new_i)

    def _on_add_spawn(self, e: object) -> None:
        if self._detail_spawn_column is None:
            return
        idx = len(self._detail_spawn_rows)
        fields, delete_btn = self._make_spawn_row({}, idx)
        self._detail_spawn_rows.append((fields, delete_btn))
        add_btn_idx = len(self._detail_spawn_column.controls) - 1
        self._detail_spawn_column.controls.insert(
            add_btn_idx,
            ft.Row(
                list(fields.values()) + [delete_btn],
                spacing=2,
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
        )
        self._detail_spawn_column.update()
        self._dirty_state.mark_dirty()
        self._refresh_button_states()

    def _delete_spawn(self, idx: int) -> None:
        if (
            idx < 0
            or idx >= len(self._detail_spawn_rows)
            or self._detail_spawn_column is None
        ):
            return
        del self._detail_spawn_rows[idx]
        spawn_row_idx = idx + 1
        del self._detail_spawn_column.controls[spawn_row_idx]
        self._detail_spawn_column.update()
        self._dirty_state.mark_dirty()
        self._refresh_button_states()
        for i in range(idx, len(self._detail_spawn_rows)):
            _, delete_btn = self._detail_spawn_rows[i]
            delete_btn.on_click = lambda e, new_i=i: self._delete_spawn(new_i)

    def _sync_detail_panel(self) -> None:
        if self._selected_row_idx is None:
            return
        row = self._rows[self._selected_row_idx]
        # Sync children
        children = []
        for row_widgets in self._detail_child_rows:
            child = {
                "type": row_widgets[0].value or "",
                "min": row_widgets[1].value or "",
                "max": row_widgets[2].value or "",
                "lootmin": row_widgets[3].value or "",
                "lootmax": row_widgets[4].value or "",
            }
            children.append(child)
        self._event_repo.set_children(row, children)
        # Sync spawns
        name = self._detail_row_key or row.values.get("name", "")
        if name:
            spawn_info = self._spawns_data.setdefault(
                name, {"positions": [], "zone": {}}
            )
            if isinstance(spawn_info, dict):
                zone = {}
                for zk, fld in self._detail_zone_fields.items():
                    zone[zk] = fld.value or ""
                spawn_info["zone"] = zone
                positions = []
                for fields, _ in self._detail_spawn_rows:
                    pos: dict[str, str] = {}
                    for k in self._detail_spawn_keys:
                        fld = fields.get(k)
                        if fld is not None and fld.value:
                            pos[k] = fld.value
                    positions.append(pos)
                spawn_info["positions"] = positions

    def _clear_selection(self) -> None:
        self._detail_container.content = self._build_placeholder()
        self._selected_row_idx = None
        self._selected_row_indices.clear()

    def _prev_page(self, e: object) -> None:
        self._sync_page_back()
        self._clear_selection()
        self._pagination.prev_page(len(self._filtered))
        self._render_page()
        self.control.update()

    def _next_page(self, e: object) -> None:
        self._sync_page_back()
        self._clear_selection()
        self._pagination.next_page(len(self._filtered))
        self._render_page()
        self.control.update()

    def _apply_filter(self, query: str) -> None:
        self._search.set_search(query)
        self._filtered = self._search.filter_rows(self._rows)

    def _on_search(self, e: object) -> None:
        self._sync_page_back()
        query = (self._search_field.value or "").strip().lower()
        self._apply_filter(query)
        self._pagination.reset()
        self._render_page()
        self.control.update()

    def _on_search_changed(self, e: object) -> None:
        if self._search_task is not None and not self._search_task.done():
            self._search_task.cancel()
        self._search_task = asyncio.create_task(self._debounced_search())

    async def _debounced_search(self) -> None:
        try:
            await asyncio.sleep(0.3)
        except asyncio.CancelledError:
            return
        self._on_search(None)

    def _render_page(self) -> None:
        total = len(self._filtered)
        total_pages = self._pagination.total_pages(total)
        self._pagination.clamp(total)

        self._dirty_state.set_syncing(True)
        self._table_ctrl.render(
            self._rows,
            self._filtered,
            self._pagination.page_index,
            self._selected_row_indices,
        )
        self._dirty_state.set_syncing(False)

        self._page_info.value = (
            f"Page {self._pagination.page_index + 1}/{total_pages}  ({total} rows)"
        )
        self._prev_btn.disabled = self._pagination.page_index <= 0
        self._next_btn.disabled = self._pagination.page_index >= total_pages - 1
        self._refresh_button_states()

    def _sync_page_back(self) -> None:
        if self._events_path is None or not self._dirty_state.is_dirty:
            return
        self._undo_mgr.record(self._undo_mgr.take_snapshot(self._rows))
        self._sync_detail_panel()
        self._table_ctrl.sync_back(
            self._rows, self._filtered, self._pagination.page_index
        )
        self._dirty_state.mark_clean()

    def _sync_widgets_to_rows(self) -> None:
        if self._events_path is None or not self._dirty_state.is_dirty:
            return
        self._table_ctrl.sync_back(
            self._rows, self._filtered, self._pagination.page_index
        )
        self._dirty_state.mark_clean()

    def _get_root(self) -> ET.Element | None:
        tree = self._cache.get_tree(self._events_path)
        return tree.getroot() if tree is not None else None

    def _on_undo(self, e: object) -> None:
        self._sync_widgets_to_rows()
        if self._undo_mgr.undo(self._rows, root=self._get_root()):
            self._dirty_state.mark_dirty()
            self._clear_selection()
            self._filtered = self._search.filter_rows(self._rows)
            self._render_page()
            self._refresh_button_states()
            self.control.update()

    def _on_redo(self, e: object) -> None:
        self._sync_widgets_to_rows()
        if self._undo_mgr.redo(self._rows, root=self._get_root()):
            self._dirty_state.mark_dirty()
            self._clear_selection()
            self._filtered = self._search.filter_rows(self._rows)
            self._render_page()
            self._refresh_button_states()
            self.control.update()

    def _refresh_button_states(self) -> None:
        self._undo_btn.disabled = not self._undo_mgr.can_undo
        self._redo_btn.disabled = not self._undo_mgr.can_redo
        self._undo_btn.update()
        self._redo_btn.update()
        self._refresh_commands()

    def save_file(self) -> None:
        self._sync_page_back()
        if self._events_path is not None:
            try:
                self._event_repo.save(self._events_path, self._rows)
                if self._spawns_path and self._spawns_data:
                    self._event_repo.save_spawns(self._spawns_path, self._spawns_data)
                self._dirty_state.mark_clean()
            except Exception as ex:
                logger.error("Auto-save failed for %s: %s", self._events_path, ex)
            if self.on_saved:
                self.on_saved()

    def clear(self) -> None:
        self._events_path = None
        self._spawns_path = None
        self._rows = []
        self._filtered = []
        self._spawns_data = {}
        self._all_spawn_keys = ["x", "z", "y", "a"]
        self._table_ctrl.clear()
        self._save_text.value = ""
        self.control.visible = False
        self._dirty_state.reset()
        self._pagination.reset()
        self._search.reset()
        self._selected_row_idx = None
        self._selected_row_indices.clear()
        self._detail_row_key = None
        self._detail_child_rows = []
        self._detail_child_column = None
        self._detail_spawn_keys = []
        self._detail_spawn_widths = {}
        self._detail_spawn_rows = []
        self._detail_spawn_column = None
        self._detail_zone_fields = {}
        logger.debug("EventDisplay cleared")

    def undo(self, e: object = None) -> None:
        self._on_undo(None)

    def redo(self, e: object = None) -> None:
        self._on_redo(None)

    def add_row(self, e: object = None) -> None:
        self._add_event()

    def delete_row(self, e: object = None) -> None:
        self._delete_selected()

    def prev_page(self, e: object = None) -> None:
        self._prev_page(None)

    def next_page(self, e: object = None) -> None:
        self._next_page(None)

    @property
    def can_undo(self) -> bool:
        return self._undo_mgr.can_undo

    @property
    def can_redo(self) -> bool:
        return self._undo_mgr.can_redo

    @property
    def can_add(self) -> bool:
        return self._events_path is not None

    @property
    def can_delete(self) -> bool:
        return bool(self._selected_row_indices)

    @property
    def can_prev(self) -> bool:
        return self.can_add and self._pagination.page_index > 0

    @property
    def can_next(self) -> bool:
        total = self._pagination.total_pages(len(self._filtered))
        return self.can_add and self._pagination.page_index < total - 1
