from __future__ import annotations

import asyncio
import json
import logging
import random
import time
import urllib.request
from collections.abc import Callable

from lxml import etree as ET

from controllers.dirty_state_manager import DirtyStateManager
from controllers.pagination_controller import PaginationController
from controllers.search_controller import (
    EMPTY_CATEGORY_MARKER,
    EMPTY_USAGE_MARKER,
    EMPTY_VALUE_MARKER,
    SearchController,
)
from controllers.table_controller import (
    TableController,
    _collect_flag_names,
    PAGE_SIZE,
    DEFAULT_FLAG_NAMES,
)
from models.field_def import (
    CATEGORIES,
    FieldDef,
    STATIC_FIELD_DEFS,
    USAGES,
    VALUES_LIST,
)
from models.row_data import RowData
from repository.file_cache import FileCache
from repository.xml_repository import XmlRepository
from models.undo_manager import UndoManager
from protocols import IXmlRepository, IDetailPanel, IBatchPanel
from services.entertainment_service import EntertainmentService
from ui.batch_panel import BatchPanel
from ui.detail_panel import DetailPanel

import flet as ft

logger = logging.getLogger(__name__)

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
    "Search filters types by name as you type \u2014 use the bar below the table",
    "Category values come from a dropdown with common DayZ categories",
    "Add Usage/Value chips using the + buttons in the right panel",
    "Remove a chip by clicking the X on it",
    "Click Save to persist all changes to the XML file",
    "Use Prev and Next buttons to navigate between pages of results",
    "Edits are tracked as dirty until you click Save",
    "Higher Lifetime values increase server memory usage; keep balanced",
    "Usage values must match the map's zone definitions for proper spawning",
    "Negative Cost can be used for quest or admin items that never spawn naturally",
    "Value tiers (e.g., Tier1, Tier2, Tier3) determine rarity across loot zones",
    "Flags: Cargo = vehicle trunks, Map = ground spawns, Player = starter gear, Hoarder = stashes",
    "Category helps group items for mod compatibility and editor filters",
    "Always set QuantMin and QuantMax to avoid over‑spawning in one container",
    "Restock interval should be shorter for high‑traffic areas to keep loot fresh",
    "Use the search bar to quickly find items by partial name or type",
    "Consider testing changes on a separate server before deploying to production",
    "Copy existing item settings as a template for creating new items",
    "Different maps (Chernarus, Livonia) may use specific zone names like 'Airfield'",
    "Nominal is a target – actual count fluctuates based on spawn chances",
    "Low Cost gives higher spawn priority – reserve it for vital items",
    "Regularly review loot tables to prevent rare item inflation and performance issues",
]


class FileDisplay:
    on_saved: Callable[[], None] | None = None

    def __init__(
        self,
        page: ft.Page,
        xml_repo: IXmlRepository | None = None,
        cache: FileCache | None = None,
        detail_panel: IDetailPanel | None = None,
        batch_panel: IBatchPanel | None = None,
        entertainment_service: EntertainmentService | None = None,
    ):
        self._page = page
        self.cache = cache or FileCache()
        self.xml_repo = xml_repo or XmlRepository(cache=self.cache)
        self._undo_mgr = UndoManager()
        self._entertainment_service = entertainment_service

        self._table_ctrl = TableController(page)
        self._pagination = PaginationController(PAGE_SIZE)
        self._search = SearchController()
        self._dirty_state = DirtyStateManager()

        self._search_task: asyncio.Task[None] | None = None
        self._tip_task: asyncio.Task[None] | None = None
        self._meow_task: asyncio.Task[None] | None = None
        self._meme_task: asyncio.Task[None] | None = None
        self._path: str | None = None
        self._rows: list[RowData] = []
        self._filtered: list[int] = []
        self._text_mode: bool = False
        self._text_editor = ft.TextField(
            multiline=True,
            min_lines=1,
            expand=True,
            dense=True,
            border=ft.InputBorder.NONE,
            on_change=self._on_text_change,
        )
        self._text_placeholder = ft.Text(
            "",
            size=11,
            selectable=True,
        )

        self._selected_row_idx: int | None = None
        self._selected_row_indices: set[int] = set()
        self._multi_select_mode: bool = False
        self._shift_pressed: bool = False
        self._mouse_down: bool = False
        self._last_clicked_row: int | None = None
        self._drag_start_slot: int | None = None

        page.on_keyboard_event = self._on_page_keyboard
        page.theme = ft.Theme(hover_color=ft.Colors.TRANSPARENT)
        page.dark_theme = ft.Theme(hover_color=ft.Colors.TRANSPARENT)

        self._table_ctrl.set_callbacks(
            on_row_click=self._on_row_click,
            on_field_change=self._on_field_change,
            on_row_hover=self._on_row_hover,
            on_row_tap_down=self._on_row_tap_down,
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
            "Prev",
            on_click=self._prev_page,
        )
        self._next_btn = ft.Button(
            "Next",
            on_click=self._next_page,
        )
        self._multi_btn = ft.Button(
            "Multi-select disabled",
            icon=ft.Icons.SELECT_ALL,
            tooltip="Toggle multi-select mode",
            on_click=self._toggle_multi_select,
            icon_color=ft.Colors.GREY,
        )
        self._save_btn = ft.Button(
            "Save",
            icon=ft.Icons.SAVE,
            on_click=self.save_current,
        )
        self._undo_btn = ft.IconButton(
            icon=ft.Icons.UNDO,
            on_click=self._on_undo,
        )
        self._redo_btn = ft.IconButton(
            icon=ft.Icons.REDO,
            on_click=self._on_redo,
        )
        self._stats_btn = ft.IconButton(
            icon=ft.Icons.BAR_CHART,
            tooltip="Show Stats",
            on_click=self._on_stats_click,
            visible=False,
        )
        self._lucky_btn = ft.IconButton(
            icon=ft.Icons.CASINO,
            tooltip="I'm Feeling Lucky",
            on_click=self._on_lucky_click,
            visible=False,
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
        self._case_sensitive_checkbox = ft.Checkbox(
            label="Case-sensitive",
            value=False,
            on_change=self._on_case_sensitive_changed,
            tooltip="Match search text exactly (case-sensitive)",
        )
        self._category_filter_values: list[str] = []
        menu_bar_style = ft.MenuStyle(
            fixed_size=ft.Size.from_height(32),
            shape=ft.RoundedRectangleBorder(radius=10),
        )
        self._category_filter_menu = ft.MenuBar(
            style=menu_bar_style,
            controls=[
                ft.SubmenuButton(
                    content=ft.Text("↑Category"),
                    controls=self._build_category_menu_items(),
                )
            ],
        )
        self._usage_filter_values: list[str] = []
        self._usage_filter_menu = ft.MenuBar(
            style=menu_bar_style,
            controls=[
                ft.SubmenuButton(
                    content=ft.Text("↑Usage"),
                    controls=self._build_usage_menu_items(),
                )
            ],
        )
        self._value_filter_values: list[str] = []
        self._value_filter_menu = ft.MenuBar(
            style=menu_bar_style,
            controls=[
                ft.SubmenuButton(
                    content=ft.Text("↑Value"),
                    controls=self._build_value_menu_items(),
                )
            ],
        )

        self._tips_switcher = ft.AnimatedSwitcher(
            content=ft.Text(
                _TIPS[0],
                size=11,
                italic=True,
                color=ft.Colors.GREY_500,
            ),
            transition=ft.AnimatedSwitcherTransition.FADE,
            duration=500,
        )
        self._detail_placeholder = ft.Container(
            content=ft.Column(
                [
                    ft.Text(
                        "Select type",
                        size=16,
                        italic=True,
                        color=ft.Colors.GREY,
                        text_align=ft.TextAlign.CENTER,
                    ),
                    ft.Container(expand=True),
                    self._tips_switcher,
                ]
            ),
            alignment=ft.Alignment.CENTER,
            expand=True,
        )
        self._detail_panel: IDetailPanel = detail_panel or DetailPanel(
            self._page,
            self._tips_switcher,
            on_changed=lambda: self._on_field_change(None),
        )
        self._batch_panel: IBatchPanel = batch_panel or BatchPanel(
            self._page,
            self._tips_switcher,
            on_batch_apply=self._on_batch_action,
        )
        self._detail_container = ft.Container(
            width=400,
            padding=10,
            content=self._detail_placeholder,
        )

        self._fab = ft.FloatingActionButton(
            icon=ft.Icons.ADD,
            on_click=self._on_fab_click,
        )

        self.button_row = ft.Row(
            [
                self._save_btn,
                self._multi_btn,
                self._undo_btn,
                self._redo_btn,
                self._lucky_btn,
                self._stats_btn,
                ft.Divider(),
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
                            self._case_sensitive_checkbox,
                            ft.Divider(),
                            self._category_filter_menu,
                            self._usage_filter_menu,
                            self._value_filter_menu,
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

        self._text_container = ft.Container(
            visible=False,
            expand=True,
            content=ft.Column(
                [
                    ft.Container(
                        content=self._text_editor,
                        border=ft.Border(
                            ft.BorderSide(1, ft.Colors.OUTLINE_VARIANT),
                            ft.BorderSide(1, ft.Colors.OUTLINE_VARIANT),
                            ft.BorderSide(1, ft.Colors.OUTLINE_VARIANT),
                            ft.BorderSide(1, ft.Colors.OUTLINE_VARIANT),
                        ),
                        border_radius=8,
                        padding=10,
                        expand=True,
                    ),
                    self._text_placeholder,
                ],
                expand=True,
            ),
        )

        logger.debug("FileDisplay initialized")

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

    @_page_idx.setter
    def _page_idx(self, value: int) -> None:
        self._pagination.page_index = value

    @property
    def _pool_fields(self) -> list[list[ft.Control]]:
        return self._table_ctrl.pool_fields

    @property
    def _pool_rows(self) -> list[ft.Container]:
        return self._table_ctrl.pool_rows

    @property
    def _field_defs(self) -> list[FieldDef]:
        return self._table_ctrl.field_defs

    @property
    def _flag_names(self) -> list[str]:
        return self._table_ctrl.flag_names

    @_flag_names.setter
    def _flag_names(self, value: list[str]) -> None:
        self._table_ctrl.flag_names = value

    @property
    def _detail_usage_set(self) -> set[str]:
        dp = self._detail_panel
        if isinstance(dp, DetailPanel) and dp._usage_chipset is not None:
            return dp._usage_chipset._values
        return set()

    @property
    def _detail_value_set(self) -> set[str]:
        dp = self._detail_panel
        if isinstance(dp, DetailPanel) and dp._value_chipset is not None:
            return dp._value_chipset._values
        return set()

    @property
    def _batch_fields(self) -> dict[str, ft.Control]:
        bp = self._batch_panel
        if isinstance(bp, BatchPanel):
            return bp._field_controls
        return {}

    @property
    def _batch_flag_checkboxes(self) -> dict[str, ft.Checkbox]:
        bp = self._batch_panel
        if isinstance(bp, BatchPanel):
            return bp._flag_checkboxes
        return {}

    def _load_setup(self, path: str) -> None:
        if self._search_task is not None and not self._search_task.done():
            self._search_task.cancel()
            self._search_task = None
        self._text_mode = False
        self._text_container.visible = False
        self.control.content = self._keyboard_listener
        self._path = path
        self._save_text.value = ""
        self._pagination.reset()
        self._search.reset()
        self._search_field.value = ""
        self._category_filter_values.clear()
        self._rebuild_category_menu()
        self._usage_filter_values.clear()
        self._rebuild_usage_menu()
        self._value_filter_values.clear()
        self._rebuild_value_menu()
        self._dirty_state.reset()
        self._undo_mgr.clear()

    def _load_finish(self) -> None:
        self._undo_mgr.record(self._undo_mgr.take_snapshot(self._rows))
        self._table_ctrl.flag_names = _collect_flag_names(self._rows)
        self._table_ctrl.init_dynamic()
        self._batch_panel.hide()
        self._detail_panel.hide()
        self._clear_selection()
        self._apply_filter("")
        self._render_page()
        self._refresh_button_states()
        self.control.visible = True
        self._page.run_task(self._keyboard_listener.focus)
        self._shift_pressed = False
        self._update_fab_icon()
        if self._tip_task is not None and not self._tip_task.done():
            self._tip_task.cancel()
        self._tip_task = asyncio.create_task(self._cycle_tip())

    def _is_text_file(self, path: str) -> bool:
        return not path.lower().endswith(".xml")

    def _load_text_file(self, path: str) -> None:
        self._text_mode = True
        self._save_text.value = ""
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                content = f.read()
        except OSError as ex:
            logger.error("Error reading text file %s: %s", path, ex)
            self._text_placeholder.value = f"Error reading file: {ex}"
            self._text_placeholder.color = ft.Colors.RED
            self.control.content = self._text_container
            self._text_container.visible = True
            self.control.visible = True
            return
        self._text_editor.value = content
        self._text_placeholder.value = path
        self._text_placeholder.color = ft.Colors.GREY
        self.control.content = self._text_container
        self._text_container.visible = True
        self.control.visible = True
        self._undo_mgr.clear()
        self._dirty_state.reset()
        logger.info("Loaded text file: %s", path)

    def load_file(self, path: str) -> None:
        self._load_setup(path)
        if self._is_text_file(path):
            self._load_text_file(path)
            return
        self._text_mode = False
        try:
            self._rows = self.xml_repo.parse_file(path)
        except Exception as ex:
            logger.error("Error loading file %s: %s", path, ex)
            self._undo_mgr.clear()
            self.control.content = ft.Container(
                content=ft.Text(f"Error parsing file: {ex}", selectable=True),
                padding=10,
            )
            self.control.visible = True
            return
        self._load_finish()
        logger.info("Loaded file: %s (%d rows)", path, len(self._rows))

    async def load_file_async(
        self,
        path: str,
        cancel_check: Callable[[], bool] | None = None,
    ) -> None:
        self._load_setup(path)
        if self._is_text_file(path):
            self._load_text_file(path)
            if cancel_check is not None and cancel_check():
                logger.info("CANCEL_CHECK cancelled load of %s", path)
                return
            try:
                self.control.update()
            except RuntimeError:
                pass
            return
        self._text_mode = False
        try:
            self._rows = await self.xml_repo.parse_file_async(path)
        except Exception as ex:
            logger.error("Error loading file %s: %s", path, ex)
            self._undo_mgr.clear()
            self.control.content = ft.Container(
                content=ft.Text(f"Error parsing file: {ex}", selectable=True),
                padding=10,
            )
            self.control.visible = True
            return
        if cancel_check is not None and cancel_check():
            logger.info("CANCEL_CHECK cancelled load of %s", path)
            return
        self._load_finish()
        self.control.update()

    def save_current(self, e: object) -> None:
        if self._text_mode:
            self._save_text_file()
            return
        self._sync_detail_panel()
        self._sync_page_back()
        if self._path is None:
            return
        try:
            self.xml_repo.save(self._path, self._rows)
            self._handle_post_save()
            self._dirty_state.mark_clean()
            logger.info("Saved %s", self._path)
            if self.on_saved:
                self.on_saved()
        except Exception as ex:
            self._save_text.value = f"Save error: {ex}"
            self._save_text.color = ft.Colors.RED
            logger.error("Save failed for %s: %s", self._path, ex)

    async def _save_async(self) -> None:
        if self._text_mode:
            self._save_text_file()
            return
        self._sync_detail_panel()
        self._sync_page_back()
        if self._path is None:
            return
        try:
            await self.xml_repo.save_async(self._path, self._rows)
            self._handle_post_save()
            self._dirty_state.mark_clean()
            logger.info("Saved (async) %s", self._path)
            if self.on_saved:
                self.on_saved()
        except Exception as ex:
            self._save_text.value = f"Save error: {ex}"
            self._save_text.color = ft.Colors.RED
            logger.error("Save failed for %s: %s", self._path, ex)
        self.control.update()

    async def _cycle_tip(self) -> None:
        idx = 0
        while True:
            try:
                await asyncio.sleep(6)
            except asyncio.CancelledError:
                return
            idx = (idx + 1) % len(_TIPS)
            if self._entertainment_service and self._entertainment_service.cat_mode:
                tip = self._entertainment_service.get_cat_tip(idx)
            else:
                tip = _TIPS[idx]
            self._tips_switcher.content = ft.Text(
                tip,
                size=11,
                italic=True,
                color=ft.Colors.GREY_500,
            )
            self._tips_switcher.update()

    def _on_text_change(self, e: object) -> None:
        self._dirty_state.mark_dirty()
        if self._save_text.value:
            self._save_text.value = ""
            self._save_text.color = None

    def _save_text_file(self) -> bool:
        if self._path is None:
            return True
        try:
            with open(self._path, "w", encoding="utf-8") as f:
                f.write(self._text_editor.value)
            self._save_text.value = ""
            self._dirty_state.mark_clean()
            logger.info("Saved text file %s", self._path)
            if self.on_saved:
                self.on_saved()
            return True
        except OSError as ex:
            self._save_text.value = f"Save error: {ex}"
            self._save_text.color = ft.Colors.RED
            logger.error("Save failed for %s: %s", self._path, ex)
            return False

    def _on_field_change(self, e: object) -> None:
        self._dirty_state.mark_dirty()
        if self._entertainment_service:
            if e is not None:
                control = getattr(e, "control", None)
                if control is not None:
                    field_key = getattr(control, "data", None)
                    if field_key:
                        self._entertainment_service.record_edit(field_key)
                        if field_key == "name":
                            name = getattr(control, "value", "")
                            self._check_easter_egg_value(name)
            achievement = self._entertainment_service.check_achievements()
            if achievement is not None:
                name = self._entertainment_service.get_achievement_name(achievement)
                if name:
                    self._page.run_task(
                        self._show_achievement_fireworks,
                        achievement,
                        name,
                    )

    def _check_easter_egg_value(self, name: str) -> None:
        if not self._entertainment_service:
            return
        egg = self._entertainment_service.check_easter_egg(name)
        if egg:
            msg, color = egg
            dialog = ft.AlertDialog(
                title=ft.Text("Easter Egg Found!", weight=ft.FontWeight.BOLD),
                content=ft.Column(
                    [
                        ft.Text(
                            msg,
                            size=18,
                            weight=ft.FontWeight.BOLD,
                            color=color,
                        ),
                    ],
                    tight=True,
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                actions=[
                    ft.TextButton("Nice!", on_click=lambda _: self._page.pop_dialog())
                ],
                actions_alignment=ft.MainAxisAlignment.CENTER,
            )
            self._page.show_dialog(dialog)
            self._page.update()

    def _on_fab_click(self, e: object) -> None:
        if self._path is None:
            return
        if self._shift_pressed:
            self._delete_selected()
        else:
            self._add_type()

    def _add_type(self) -> None:
        self._sync_detail_panel()

        tree = self.cache.get_tree(self._path)
        if tree is None:
            return
        root = tree.getroot()

        new_elem = ET.SubElement(root, "type")
        new_elem.set("name", "")

        new_row = RowData(values={}, flags={}, elem=new_elem)
        for fd in STATIC_FIELD_DEFS:
            new_row.values[fd.key] = "" if fd.key == "name" else "0"
        for fn in DEFAULT_FLAG_NAMES:
            new_row.flags[fn] = "0"

        self._undo_mgr.record(self._undo_mgr.take_snapshot(self._rows))
        self._rows.insert(0, new_row)
        self._apply_filter(self._search_field.value or "")
        self._selected_row_idx = 0
        self._selected_row_indices = {0}
        self._pagination.reset()
        self._dirty_state.mark_dirty()
        self._render_page()
        self._load_detail_panel()
        self._update_detail_panel()
        self.control.update()

    def _delete_selected(self) -> None:
        if not self._selected_row_indices:
            return

        names = [
            self._rows[idx].values.get("name", "") or "(unnamed)"
            for idx in sorted(self._selected_row_indices)
        ]

        def _reset_shift(ev: object) -> None:
            self._shift_pressed = False
            self._mouse_down = False
            self._update_fab_icon()

        def confirm(ev: object) -> None:
            _reset_shift(ev)
            self._page.pop_dialog()
            self._perform_delete()

        def cancel(ev: object) -> None:
            _reset_shift(ev)
            self._page.pop_dialog()

        if len(names) == 1:
            title = "Delete Type"
            message = f'Delete type "{names[0]}"?'
        else:
            title = "Delete Types"
            shown = ", ".join(f'"{n}"' for n in names[:3])
            if len(names) > 3:
                shown += f" and {len(names) - 3} more"
            message = f"Delete {len(names)} types?\n{shown}"

        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text(title),
            content=ft.Text(message),
            actions=[
                ft.TextButton("Cancel", on_click=cancel),
                ft.TextButton("Delete", on_click=confirm),
            ],
        )
        self._page.show_dialog(dialog)
        self._page.update()

    def _perform_delete(self) -> None:
        if not self._selected_row_indices:
            return

        self._sync_detail_panel()
        self._sync_page_back()

        tree = self.cache.get_tree(self._path)
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
            self._mouse_down = False
            self._update_fab_icon()

    def _on_page_keyboard(self, e: ft.KeyboardEvent) -> None:
        self._shift_pressed = e.shift
        self._update_fab_icon()
        if not e.shift:
            self._mouse_down = False

    def _toggle_multi_select(self, e: object) -> None:
        self._multi_select_mode = not self._multi_select_mode
        self._multi_btn.content = (
            ft.Text("Multi-select enabled")
            if self._multi_select_mode
            else ft.Text("Multi-select disabled")
        )
        self._multi_btn.icon_color = (
            ft.Colors.PRIMARY if self._multi_select_mode else ft.Colors.GREY
        )
        self._multi_btn.update()

    def _on_row_click(self, pool_slot: int) -> None:
        start = self._pagination.page_index * PAGE_SIZE
        actual_idx = (
            self._filtered[start + pool_slot]
            if start + pool_slot < len(self._filtered)
            else -1
        )
        if actual_idx < 0:
            return
        if (
            actual_idx == self._last_clicked_row
            and time.monotonic() - getattr(self, "_last_click_time", 0) < 0.1
        ):
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

    def _on_row_tap_down(self, e: object, pool_slot: int) -> None:
        self._mouse_down = True
        self._drag_start_slot = pool_slot

    def _on_row_hover(self, e: ft.ControlEvent, pool_slot: int) -> None:
        if not e.data:
            return
        if not self._shift_pressed or not self._mouse_down:
            return
        start = self._pagination.page_index * PAGE_SIZE

        if self._drag_start_slot is not None:
            start_idx = (
                self._filtered[start + self._drag_start_slot]
                if start + self._drag_start_slot < len(self._filtered)
                else -1
            )
            self._drag_start_slot = None
            if start_idx >= 0 and start_idx not in self._selected_row_indices:
                self._selected_row_indices.add(start_idx)
                self._selected_row_idx = start_idx
                self._render_page()
                self.control.update()

        actual_idx = (
            self._filtered[start + pool_slot]
            if start + pool_slot < len(self._filtered)
            else -1
        )
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
            self._undo_mgr.record(self._undo_mgr.take_snapshot(self._rows))
            if hasattr(self._detail_panel, "_usage_chipset") and hasattr(
                self._detail_panel, "_value_chipset"
            ):
                usage_chipset = getattr(
                    self._detail_panel,
                    "_usage_chipset",
                    None,
                )
                value_chipset = getattr(
                    self._detail_panel,
                    "_value_chipset",
                    None,
                )
                if usage_chipset and value_chipset:
                    usage = ", ".join(usage_chipset.get_values())
                    value = ", ".join(value_chipset.get_values())
                    self._rows[self._selected_row_idx].values["usage"] = usage
                    self._rows[self._selected_row_idx].values["value"] = value
                    if usage or value:
                        self._dirty_state.mark_dirty()

    def _update_detail_panel(self) -> None:
        if len(self._selected_row_indices) >= 2:
            self._batch_panel.show(
                f"Batch edit: {len(self._selected_row_indices)} rows selected",
                USAGES,
                VALUES_LIST,
                self._table_ctrl.flag_names,
            )
            self._detail_container.content = self._batch_panel.build()
        elif len(self._selected_row_indices) == 1:
            self._detail_container.content = self._detail_panel.build()
        else:
            self._detail_container.content = self._detail_placeholder

    def _load_detail_panel(self) -> None:
        if self._selected_row_idx is None:
            return
        row = self._rows[self._selected_row_idx]
        self._detail_panel.show(row, USAGES, VALUES_LIST)

    def _on_detail_usage_add(self, v: str) -> None:
        if (
            hasattr(self._detail_panel, "_usage_chipset")
            and self._detail_panel._usage_chipset
        ):
            self._detail_panel._usage_chipset.add(v)

    def _detail_remove_usage(self, v: str) -> None:
        if (
            hasattr(self._detail_panel, "_usage_chipset")
            and self._detail_panel._usage_chipset
        ):
            self._detail_panel._usage_chipset.remove(v)

    def _on_detail_value_add(self, v: str) -> None:
        if (
            hasattr(self._detail_panel, "_value_chipset")
            and self._detail_panel._value_chipset
        ):
            self._detail_panel._value_chipset.add(v)

    def _detail_remove_value(self, v: str) -> None:
        if (
            hasattr(self._detail_panel, "_value_chipset")
            and self._detail_panel._value_chipset
        ):
            self._detail_panel._value_chipset.remove(v)

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
        w = self._batch_fields.get(field_key)
        if w is None:
            return
        value = w.value or ""
        for idx in self._selected_row_indices:
            self._rows[idx].values[field_key] = value
        self._dirty_state.mark_dirty()
        self._render_page()
        self._save_text.value = (
            f"{field_key} applied to {len(self._selected_row_indices)} rows"
        )
        self._save_text.color = ft.Colors.GREEN
        self.control.update()

    def _batch_save_category(self) -> None:
        self._undo_mgr.record(self._undo_mgr.take_snapshot(self._rows))
        self._sync_page_back()
        w = self._batch_fields.get("category")
        if w is None:
            return
        value = w.value or ""
        for idx in self._selected_row_indices:
            self._rows[idx].values["category"] = value
        self._dirty_state.mark_dirty()
        self._render_page()
        self._save_text.value = (
            f"Category applied to {len(self._selected_row_indices)} rows"
        )
        self._save_text.color = ft.Colors.GREEN
        self.control.update()

    def _batch_save_usage(self) -> None:
        self._undo_mgr.record(self._undo_mgr.take_snapshot(self._rows))
        self._sync_page_back()
        bp = getattr(self._batch_panel, "_usage_chipset", None)
        parts = ", ".join(bp.get_values()) if bp else ""
        for idx in self._selected_row_indices:
            self._rows[idx].values["usage"] = parts
        self._dirty_state.mark_dirty()
        self._render_page()
        self._save_text.value = (
            f"Usage applied to {len(self._selected_row_indices)} rows"
        )
        self._save_text.color = ft.Colors.GREEN
        self.control.update()

    def _batch_save_value(self) -> None:
        self._undo_mgr.record(self._undo_mgr.take_snapshot(self._rows))
        self._sync_page_back()
        bp = getattr(self._batch_panel, "_value_chipset", None)
        parts = ", ".join(bp.get_values()) if bp else ""
        for idx in self._selected_row_indices:
            self._rows[idx].values["value"] = parts
        self._dirty_state.mark_dirty()
        self._render_page()
        self._save_text.value = (
            f"Value applied to {len(self._selected_row_indices)} rows"
        )
        self._save_text.color = ft.Colors.GREEN
        self.control.update()

    def _batch_save_flag(self, flag_name: str) -> None:
        self._undo_mgr.record(self._undo_mgr.take_snapshot(self._rows))
        self._sync_page_back()
        cb = self._batch_flag_checkboxes.get(flag_name)
        if cb is None:
            return
        value = "1" if cb.value else "0"
        for idx in self._selected_row_indices:
            self._rows[idx].flags[flag_name] = value
        self._dirty_state.mark_dirty()
        self._render_page()
        self._save_text.value = (
            f"{flag_name} applied to {len(self._selected_row_indices)} rows"
        )
        self._save_text.color = ft.Colors.GREEN
        self.control.update()

    def _clear_selection(self) -> None:
        self._mouse_down = False
        self._detail_panel.hide()
        self._detail_container.content = self._detail_placeholder
        self._selected_row_idx = None
        self._selected_row_indices.clear()

    def _prev_page(self, e: object) -> None:
        self._sync_detail_panel()
        self._sync_page_back()
        self._clear_selection()
        self._pagination.prev_page(len(self._filtered))
        self._render_page()
        self.control.update()

    def _next_page(self, e: object) -> None:
        self._sync_detail_panel()
        self._sync_page_back()
        self._clear_selection()
        self._pagination.next_page(len(self._filtered))
        self._render_page()
        self.control.update()

    def _apply_filter(self, query: str) -> None:
        self._search.set_search(
            query,
            case_sensitive=self._case_sensitive_checkbox.value,
        )
        self._search.set_filters(
            category="|".join(self._category_filter_values),
            usage="|".join(self._usage_filter_values),
            value="|".join(self._value_filter_values),
        )
        self._filtered = self._search.filter_rows(self._rows)

    def _on_search(self, e: object) -> None:
        self._sync_detail_panel()
        self._sync_page_back()
        query = (self._search_field.value or "").strip()
        self._apply_filter(query)
        self._pagination.reset()
        self._render_page()
        self.control.update()

    def _on_search_changed(self, e: object) -> None:
        if self._search_task is not None and not self._search_task.done():
            self._search_task.cancel()
        self._search_task = self._page.run_task(self._debounced_search)

    def _on_case_sensitive_changed(self, e: object) -> None:
        self._on_search(None)

    def _on_filter_changed(self, e: object) -> None:
        if self._search_task is not None and not self._search_task.done():
            self._search_task.cancel()
        self._search_task = self._page.run_task(self._debounced_search)

    async def _debounced_search(self) -> None:
        try:
            await asyncio.sleep(0.3)
        except asyncio.CancelledError:
            return
        self._on_search(None)

    def _build_category_menu_items(self) -> list[ft.MenuItemButton]:
        is_cat = self._entertainment_service and self._entertainment_service.cat_mode
        icon_fn = ft.Icons.PETS if is_cat else ft.Icons.CHECK
        items = []
        for cat in CATEGORIES:
            selected = cat in self._category_filter_values
            items.append(
                ft.MenuItemButton(
                    content=ft.Text(cat),
                    leading=ft.Icon(icon_fn) if selected else None,
                    on_click=lambda _, c=cat: self._on_category_menu_click(c),
                    close_on_click=False,
                )
            )
        empty_selected = EMPTY_CATEGORY_MARKER in self._category_filter_values
        items.append(
            ft.MenuItemButton(
                content=ft.Text("(empty)"),
                leading=ft.Icon(icon_fn) if empty_selected else None,
                on_click=lambda _: self._on_category_menu_click(EMPTY_CATEGORY_MARKER),
                close_on_click=False,
            )
        )
        return items

    def _on_category_menu_click(self, cat: str) -> None:
        if cat in self._category_filter_values:
            self._category_filter_values.remove(cat)
        else:
            self._category_filter_values.append(cat)
        self._rebuild_category_menu()
        self._on_search(None)

    def _rebuild_category_menu(self) -> None:
        for ctrl in self._category_filter_menu.controls:
            if isinstance(ctrl, ft.SubmenuButton):
                ctrl.controls = self._build_category_menu_items()
                ctrl.update()

    def _build_usage_menu_items(self) -> list[ft.MenuItemButton]:
        is_cat = self._entertainment_service and self._entertainment_service.cat_mode
        icon_fn = ft.Icons.PETS if is_cat else ft.Icons.CHECK
        items = []
        for val in USAGES:
            selected = val in self._usage_filter_values
            items.append(
                ft.MenuItemButton(
                    content=ft.Text(val),
                    leading=ft.Icon(icon_fn) if selected else None,
                    on_click=lambda _, v=val: self._on_usage_menu_click(v),
                    close_on_click=False,
                )
            )
        empty_selected = EMPTY_USAGE_MARKER in self._usage_filter_values
        items.append(
            ft.MenuItemButton(
                content=ft.Text("(empty)"),
                leading=ft.Icon(icon_fn) if empty_selected else None,
                on_click=lambda _: self._on_usage_menu_click(EMPTY_USAGE_MARKER),
                close_on_click=False,
            )
        )
        return items

    def _on_usage_menu_click(self, val: str) -> None:
        if val in self._usage_filter_values:
            self._usage_filter_values.remove(val)
        else:
            self._usage_filter_values.append(val)
        self._rebuild_usage_menu()
        self._on_search(None)

    def _rebuild_usage_menu(self) -> None:
        for ctrl in self._usage_filter_menu.controls:
            if isinstance(ctrl, ft.SubmenuButton):
                ctrl.controls = self._build_usage_menu_items()
                ctrl.update()

    def _build_value_menu_items(self) -> list[ft.MenuItemButton]:
        is_cat = self._entertainment_service and self._entertainment_service.cat_mode
        icon_fn = ft.Icons.PETS if is_cat else ft.Icons.CHECK
        items = []
        for val in VALUES_LIST:
            selected = val in self._value_filter_values
            items.append(
                ft.MenuItemButton(
                    content=ft.Text(val),
                    leading=ft.Icon(icon_fn) if selected else None,
                    on_click=lambda _, v=val: self._on_value_menu_click(v),
                    close_on_click=False,
                )
            )
        empty_selected = EMPTY_VALUE_MARKER in self._value_filter_values
        items.append(
            ft.MenuItemButton(
                content=ft.Text("(empty)"),
                leading=ft.Icon(icon_fn) if empty_selected else None,
                on_click=lambda _: self._on_value_menu_click(EMPTY_VALUE_MARKER),
                close_on_click=False,
            )
        )
        return items

    def _on_value_menu_click(self, val: str) -> None:
        if val in self._value_filter_values:
            self._value_filter_values.remove(val)
        else:
            self._value_filter_values.append(val)
        self._rebuild_value_menu()
        self._on_search(None)

    def _rebuild_value_menu(self) -> None:
        for ctrl in self._value_filter_menu.controls:
            if isinstance(ctrl, ft.SubmenuButton):
                ctrl.controls = self._build_value_menu_items()
                ctrl.update()

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

    def _sync_page_back(self) -> None:
        if self._path is None or not self._dirty_state.is_dirty:
            return
        self._undo_mgr.record(self._undo_mgr.take_snapshot(self._rows))
        self._table_ctrl.sync_back(
            self._rows, self._filtered, self._pagination.page_index
        )
        self._dirty_state.mark_clean()

    def _sync_widgets_to_rows(self) -> None:
        if self._path is None or not self._dirty_state.is_dirty:
            return
        self._table_ctrl.sync_back(
            self._rows, self._filtered, self._pagination.page_index
        )
        self._dirty_state.mark_clean()

    def _get_root(self) -> ET.Element | None:
        tree = self.cache.get_tree(self._path)
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

    def update_funny_visibility(self) -> None:
        if not self._entertainment_service:
            return
        visible = self._entertainment_service.funny_enabled
        self._lucky_btn.visible = visible
        self._stats_btn.visible = visible
        self._lucky_btn.update()
        self._stats_btn.update()

    def _try_update(self, ctrl: ft.Control) -> None:
        try:
            ctrl.update()
        except RuntimeError:
            pass

    def update_cat_icons(self) -> None:
        if not self._entertainment_service:
            return
        is_cat = self._entertainment_service.cat_mode
        self._save_btn.icon = ft.Icons.PETS if is_cat else ft.Icons.SAVE
        self._multi_btn.icon = ft.Icons.PETS if is_cat else ft.Icons.SELECT_ALL
        self._undo_btn.icon = ft.Icons.PETS if is_cat else ft.Icons.UNDO
        self._redo_btn.icon = ft.Icons.PETS if is_cat else ft.Icons.REDO
        self._lucky_btn.icon = ft.Icons.CASINO if not is_cat else ft.Icons.PETS
        self._stats_btn.icon = ft.Icons.BAR_CHART if not is_cat else ft.Icons.PETS
        self._search_field.icon = ft.Icons.PETS if is_cat else ft.Icons.SEARCH
        for ctrl in (
            self._save_btn,
            self._multi_btn,
            self._undo_btn,
            self._redo_btn,
            self._lucky_btn,
            self._stats_btn,
            self._search_field,
        ):
            self._try_update(ctrl)
        self._rebuild_category_menu()
        self._rebuild_usage_menu()
        self._rebuild_value_menu()
        self._update_fab_icon()
        self._update_chipset_cat_icons(is_cat)

    def _update_chipset_cat_icons(self, is_cat: bool) -> None:
        dp = self._detail_panel
        if isinstance(dp, DetailPanel):
            dp.set_cat_mode(is_cat)
        bp = self._batch_panel
        if isinstance(bp, BatchPanel):
            bp.set_cat_mode(is_cat)

    def _update_fab_icon(self) -> None:
        if self._entertainment_service and self._entertainment_service.cat_mode:
            self._fab.icon = ft.Icons.PETS
        else:
            self._fab.icon = ft.Icons.DELETE if self._shift_pressed else ft.Icons.ADD
        self._try_update(self._fab)

    async def show_meow_popup(self) -> None:
        meow = ft.Container(
            content=ft.Text(
                "Meow!",
                size=36,
                weight=ft.FontWeight.BOLD,
                color=ft.Colors.PINK_ACCENT,
            ),
            bgcolor=ft.Colors.with_opacity(0.7, ft.Colors.WHITE),
            border_radius=10,
            padding=20,
        )
        self._page.overlay.append(meow)
        self._page.update()
        await asyncio.sleep(0.8)
        try:
            self._page.overlay.remove(meow)
            self._page.update()
        except ValueError:
            pass

    def _handle_post_save(self) -> None:
        if not self._entertainment_service:
            self._save_text.value = "Saved"
            self._save_text.color = ft.Colors.GREEN
            return

        if self._entertainment_service.terminal_mode:
            self._page.run_task(self._show_terminal_save)
        elif self._entertainment_service.fun_save_messages:
            self._save_text.value = self._entertainment_service.get_fun_save_message()
            self._save_text.color = ft.Colors.GREEN
        else:
            self._save_text.value = "Saved"
            self._save_text.color = ft.Colors.GREEN

        if self._entertainment_service.show_meme_on_save:
            self._page.run_task(self._show_meme_dialog)

        if self._entertainment_service.cat_mode:
            self._page.run_task(self.show_meow_popup)

    async def _show_terminal_save(self) -> None:
        lines = [
            "> Saving types.xml...",
            f"> Parsing {len(self._rows)} entries...",
            "> Writing XML...",
            "> Done. 0 errors, 0 warnings.",
        ]
        self._save_text.font_family = "monospace"
        self._save_text.color = ft.Colors.GREEN_ACCENT_700
        output_lines = []
        for line in lines:
            output_lines.append(line)
            self._save_text.value = "\n".join(output_lines)
            self._save_text.update()
            await asyncio.sleep(0.35)
        await asyncio.sleep(2)
        self._save_text.font_family = None
        self._save_text.value = "Saved"
        self._save_text.color = ft.Colors.GREEN
        self._save_text.update()

    async def _show_meme_dialog(self) -> None:
        url = None
        try:
            req = urllib.request.Request(
                "https://meme-api.com/gimme",
                headers={"User-Agent": "types-editor/0.2.1"},
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode())
            url = data.get("url") or data.get("preview", [None])[-1]
        except Exception as ex:
            logger.debug("Meme fetch failed: %s", ex)
            return
        if not url:
            return
        dialog = ft.AlertDialog(
            title=ft.Text("Meme of the moment"),
            content=ft.Column(
                [
                    ft.Image(
                        src=url,
                        height=300,
                        fit=ft.ImageFit.CONTAIN,
                    ),
                ],
                tight=True,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            actions=[
                ft.TextButton(
                    "Close",
                    on_click=lambda _: self._page.pop_dialog(),
                )
            ],
        )
        self._page.show_dialog(dialog)
        self._page.update()

    def _on_stats_click(self, e: object) -> None:
        if not self._entertainment_service:
            return
        text = self._entertainment_service.get_stats_text()
        dialog = ft.AlertDialog(
            title=ft.Text("Edit Statistics", weight=ft.FontWeight.BOLD),
            content=ft.Container(
                content=ft.Text(
                    text,
                    font_family="monospace",
                    size=13,
                ),
                padding=10,
            ),
            actions=[
                ft.TextButton(
                    "Close",
                    on_click=lambda _: self._page.pop_dialog(),
                )
            ],
        )
        self._page.show_dialog(dialog)
        self._page.update()

    def _on_lucky_click(self, e: object) -> None:
        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("Feeling lucky?"),
            content=ft.Text(
                "This will randomize ALL values in SELECTED rows!\nAre you sure?"
            ),
            actions=[
                ft.TextButton(
                    "Cancel",
                    on_click=lambda _: self._page.pop_dialog(),
                ),
                ft.TextButton(
                    "LUCKY!",
                    on_click=self._do_lucky,
                ),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        self._page.show_dialog(dialog)
        self._page.update()

    def _do_lucky(self, e: object) -> None:
        self._page.pop_dialog()
        self._sync_detail_panel()
        self._sync_page_back()
        self._undo_mgr.record(self._undo_mgr.take_snapshot(self._rows))

        target_indices = (
            self._selected_row_indices
            if self._selected_row_indices
            else set(range(len(self._rows)))
        )
        for idx in target_indices:
            row = self._rows[idx]
            row.values["nominal"] = str(random.randint(1, 200))
            row.values["lifetime"] = str(
                random.choice(
                    [
                        300,
                        600,
                        1800,
                        3600,
                        7200,
                        14400,
                        28800,
                        43200,
                        86400,
                    ]
                )
            )
            row.values["restock"] = str(
                random.choice(
                    [
                        60,
                        120,
                        300,
                        600,
                        900,
                        1800,
                        3600,
                        7200,
                    ]
                )
            )
            row.values["min"] = str(random.randint(0, 50))
            row.values["quantmin"] = str(random.randint(-1, 10))
            row.values["quantmax"] = str(random.randint(1, 50))
            row.values["cost"] = str(random.randint(-1, 500))
            row.values["category"] = random.choice(CATEGORIES)
            row.values["usage"] = ", ".join(random.sample(USAGES, random.randint(1, 3)))
            row.values["value"] = random.choice(VALUES_LIST)
            for flag in row.flags:
                row.flags[flag] = random.choice(["0", "1"])

        self._dirty_state.mark_dirty()
        self._filtered = self._search.filter_rows(self._rows)
        self._render_page()
        self.control.update()

        phrase = (
            self._entertainment_service.get_lucky_phrase()
            if self._entertainment_service
            else "Done!"
        )
        success_dialog = ft.AlertDialog(
            title=ft.Text("Randomization Complete!"),
            content=ft.Text(phrase, size=16, weight=ft.FontWeight.BOLD),
            actions=[ft.TextButton("OK", on_click=lambda _: self._page.pop_dialog())],
        )
        self._page.show_dialog(success_dialog)
        self._page.update()

    async def _show_achievement_fireworks(self, threshold: int, name: str) -> None:
        chars = ["*", "✦", "✧", "★", "☆"]
        content_text = ft.Text(
            "",
            size=14,
            text_align=ft.TextAlign.CENTER,
            font_family="monospace",
        )
        total = (
            self._entertainment_service.total_edits
            if self._entertainment_service
            else 0
        )
        dialog = ft.AlertDialog(
            title=ft.Text(f"Achievement Unlocked: {name}!", weight=ft.FontWeight.BOLD),
            content=ft.Column(
                [
                    ft.Text(f"{total} total edits", size=13, color=ft.Colors.GREY_600),
                    ft.Divider(height=4),
                    content_text,
                ],
                tight=True,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            actions=[
                ft.TextButton("Continue", on_click=lambda _: self._page.pop_dialog())
            ],
            actions_alignment=ft.MainAxisAlignment.CENTER,
        )
        self._page.show_dialog(dialog)
        self._page.update()
        for _ in range(15):
            lines = "\n".join(
                "  " + "".join(random.choice(chars) for _ in range(12)) + "  "
                for _ in range(3)
            )
            content_text.value = lines
            content_text.update()
            await asyncio.sleep(0.15)

    def save_file(self) -> None:
        if self._text_mode:
            self._save_text_file()
            return
        self._sync_detail_panel()
        self._sync_page_back()
        if self._path is not None:
            try:
                self.xml_repo.save(self._path, self._rows)
                self._dirty_state.mark_clean()
            except Exception as ex:
                logger.error("Auto-save failed for %s: %s", self._path, ex)
            if self.on_saved:
                self.on_saved()

    def clear_cache(self, path: str) -> None:
        self.xml_repo.invalidate_cache(path)

    def clear(self) -> None:
        self._path = None
        self._rows = []
        self._filtered = []
        self._text_mode = False
        self._text_container.visible = False
        self.control.content = self._keyboard_listener
        self._table_ctrl.clear()
        self._save_text.value = ""
        self._category_filter_values.clear()
        self._rebuild_category_menu()
        self._usage_filter_values.clear()
        self._rebuild_usage_menu()
        self._value_filter_values.clear()
        self._rebuild_value_menu()
        self.control.visible = False
        self._dirty_state.reset()
        self._pagination.reset()
        self._search.reset()
        self._selected_row_idx = None
        self._selected_row_indices.clear()
        self._detail_panel.hide()
        self._detail_container.content = self._detail_placeholder
        self._batch_panel.hide()

        if self._tip_task is not None and not self._tip_task.done():
            self._tip_task.cancel()
        self._tip_task = None
        logger.debug("FileDisplay cleared")
