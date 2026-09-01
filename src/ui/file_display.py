from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable

from lxml import etree as ET

from commands.registry import CommandRegistry
from controllers.file_session import FileSession
from controllers.table_controller import (
    TableController,
    _collect_flag_names,
    PAGE_SIZE,
)
from models.field_def import (
    CATEGORIES,
    FieldDef,
    USAGES,
    VALUES_LIST,
)
from models.row_data import RowData
from repository.file_cache import FileCache
from repository.xml_repository import XmlRepository
from core.protocols import IXmlRepository, IDetailPanel, IBatchPanel
from services.entertainment_service import EntertainmentService
from ui.batch_panel import BatchPanel
from ui.detail_panel import DetailPanel
from ui.filter_menu import FilterMenu, FilterSpec
from ui.fun_presenter import FunPresenter

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
    "Always set QuantMin and QuantMax to avoid over\u2011spawning in one container",
    "Restock interval should be shorter for high\u2011traffic areas to keep loot fresh",
    "Use the search bar to quickly find items by partial name or type",
    "Consider testing changes on a separate server before deploying to production",
    "Copy existing item settings as a template for creating new items",
    "Different maps (Chernarus, Livonia) may use specific zone names like 'Airfield'",
    "Nominal is a target \u2013 actual count fluctuates based on spawn chances",
    "Low Cost gives higher spawn priority \u2013 reserve it for vital items",
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
        fun_presenter: FunPresenter | None = None,
        session: FileSession | None = None,
        commands: CommandRegistry | None = None,
    ):
        self._page = page
        self.cache = cache or FileCache()
        self.xml_repo = xml_repo or XmlRepository(cache=self.cache)
        self._session = session or FileSession(self.xml_repo, self.cache)
        self._entertainment_service = entertainment_service
        self._commands = commands

        self._table_ctrl = TableController(page)

        self._search_task: asyncio.Task[None] | None = None
        self._tip_task: asyncio.Task[None] | None = None
        self._meow_task: asyncio.Task[None] | None = None
        self._meme_task: asyncio.Task[None] | None = None
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
            on_click=self._bind("prev_page", self._prev_page),
        )
        self._next_btn = ft.Button(
            "Next",
            on_click=self._bind("next_page", self._next_page),
        )
        self._multi_btn = ft.Button(
            "Multi-select disabled",
            icon=ft.Icons.SELECT_ALL,
            tooltip="Toggle multi-select mode",
            on_click=self._bind("toggle_multi_select", self._toggle_multi_select),
            icon_color=ft.Colors.GREY,
        )
        self._save_btn = ft.Button(
            "Save",
            icon=ft.Icons.SAVE,
            on_click=self._bind("save", self.save_current),
        )
        self._undo_btn = ft.IconButton(
            icon=ft.Icons.UNDO,
            on_click=self._bind("undo", self._on_undo),
        )
        self._redo_btn = ft.IconButton(
            icon=ft.Icons.REDO,
            on_click=self._bind("redo", self._on_redo),
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
        self._filter_specs: list[FilterSpec] = [
            FilterSpec(
                key="category",
                label="↑Category",
                options=CATEGORIES,
                empty_marker="__empty__",
            ),
            FilterSpec(
                key="usage",
                label="↑Usage",
                options=USAGES,
                empty_marker="__usage_empty__",
            ),
            FilterSpec(
                key="value",
                label="↑Value",
                options=VALUES_LIST,
                empty_marker="__value_empty__",
            ),
        ]
        self._filter_menus: dict[str, FilterMenu] = {
            spec.key: FilterMenu(
                spec=spec,
                on_changed=lambda: self._on_search(None),
                is_cat=lambda: bool(
                    self._entertainment_service
                    and self._entertainment_service.cat_mode
                ),
            )
            for spec in self._filter_specs
        }

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
        self._fun = fun_presenter or FunPresenter(
            page,
            entertainment_service,
            self._tips_switcher,
            self._save_text,
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
                            *[self._filter_menus[s.key].menu for s in self._filter_specs],
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
        return self._session.dirty

    @_dirty.setter
    def _dirty(self, value: bool) -> None:
        if value:
            self._session.mark_dirty()
        else:
            self._session.mark_clean()

    @property
    def _page_idx(self) -> int:
        return self._session.page_index

    @_page_idx.setter
    def _page_idx(self, value: int) -> None:
        self._session.page_index = value

    @property
    def _rows(self) -> list[RowData]:
        return self._session.rows

    @_rows.setter
    def _rows(self, value: list[RowData]) -> None:
        self._session.rows = value

    @property
    def _filtered(self) -> list[int]:
        return self._session.filtered

    @property
    def _path(self) -> str | None:
        return self._session.path

    @_path.setter
    def _path(self, value: str | None) -> None:
        self._session.path = value

    @property
    def _selected_row_idx(self) -> int | None:
        return self._session.selected_row_idx

    @_selected_row_idx.setter
    def _selected_row_idx(self, value: int | None) -> None:
        self._session.selected_row_idx = value

    @property
    def _selected_row_indices(self) -> set[int]:
        return self._session.selected_row_indices

    @_selected_row_indices.setter
    def _selected_row_indices(self, value: set[int]) -> None:
        self._session.selected_row_indices = value

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
        self._session.load_setup(path)
        self._save_text.value = ""
        self._search_field.value = ""
        for menu in self._filter_menus.values():
            menu.clear()

    def _load_finish(self) -> None:
        self._table_ctrl.flag_names = _collect_flag_names(self._session.rows)
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
        self._tip_task = asyncio.create_task(self._fun.cycle_tip(_TIPS))

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
        self._session.reset_transient()
        logger.info("Loaded text file: %s", path)

    def load_file(self, path: str) -> None:
        self._load_setup(path)
        if self._is_text_file(path):
            self._load_text_file(path)
            return
        self._text_mode = False
        try:
            self._session.rows = self.xml_repo.parse_file(path)
        except Exception as ex:
            logger.error("Error loading file %s: %s", path, ex)
            self._session.reset_transient()
            self.control.content = ft.Container(
                content=ft.Text(f"Error parsing file: {ex}", selectable=True),
                padding=10,
            )
            self.control.visible = True
            return
        self._load_finish()
        logger.info("Loaded file: %s (%d rows)", path, len(self._session.rows))

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
            self._session.rows = await self.xml_repo.parse_file_async(path)
        except Exception as ex:
            logger.error("Error loading file %s: %s", path, ex)
            self._session.reset_transient()
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
        if self._session.path is None:
            return
        try:
            self._session.save()
            self._handle_post_save()
            self._session.mark_clean()
            logger.info("Saved %s", self._session.path)
            if self.on_saved:
                self.on_saved()
        except Exception as ex:
            self._save_text.value = f"Save error: {ex}"
            self._save_text.color = ft.Colors.RED
            logger.error("Save failed for %s: %s", self._session.path, ex)

    def undo(self, e: object = None) -> None:
        self._on_undo(None)

    def redo(self, e: object = None) -> None:
        self._on_redo(None)

    def add_row(self, e: object = None) -> None:
        self._add_type()

    def delete_row(self, e: object = None) -> None:
        self._delete_selected()

    def toggle_multi_select(self, e: object = None) -> None:
        self._toggle_multi_select(None)

    def prev_page(self, e: object = None) -> None:
        self._prev_page(None)

    def next_page(self, e: object = None) -> None:
        self._next_page(None)

    @property
    def can_undo(self) -> bool:
        return self._session.can_undo

    @property
    def can_redo(self) -> bool:
        return self._session.can_redo

    @property
    def can_add(self) -> bool:
        return self._session.path is not None

    @property
    def can_delete(self) -> bool:
        return bool(self._session.selected_row_indices)

    @property
    def can_prev(self) -> bool:
        return self.can_add and self._session.page_index > 0

    @property
    def can_next(self) -> bool:
        return (
            self.can_add
            and self._session.page_index < self._session.total_pages() - 1
        )

    @property
    def can_toggle_multi_select(self) -> bool:
        return True

    @property
    def multi_select_mode(self) -> bool:
        return self._multi_select_mode

    async def _save_async(self) -> None:
        if self._text_mode:
            self._save_text_file()
            return
        self._sync_detail_panel()
        self._sync_page_back()
        if self._session.path is None:
            return
        try:
            await self._session.save_async()
            self._handle_post_save()
            self._session.mark_clean()
            logger.info("Saved (async) %s", self._session.path)
            if self.on_saved:
                self.on_saved()
        except Exception as ex:
            self._save_text.value = f"Save error: {ex}"
            self._save_text.color = ft.Colors.RED
            logger.error("Save failed for %s: %s", self._session.path, ex)
        self.control.update()

    def _on_text_change(self, e: object) -> None:
        self._session.mark_dirty()
        if self._save_text.value:
            self._save_text.value = ""
            self._save_text.color = None

    def _save_text_file(self) -> bool:
        if self._session.path is None:
            return True
        try:
            with open(self._session.path, "w", encoding="utf-8") as f:
                f.write(self._text_editor.value)
            self._save_text.value = ""
            self._session.mark_clean()
            logger.info("Saved text file %s", self._session.path)
            if self.on_saved:
                self.on_saved()
            return True
        except OSError as ex:
            self._save_text.value = f"Save error: {ex}"
            self._save_text.color = ft.Colors.RED
            logger.error("Save failed for %s: %s", self._session.path, ex)
            return False

    def _on_field_change(self, e: object) -> None:
        if not self._session.dirty or not self._session.can_undo:
            self._session.record_undo()
            self._refresh_button_states()
        self._session.mark_dirty()
        self._fun.on_field_change(e)

    def _on_fab_click(self, e: object) -> None:
        if self._session.path is None:
            return
        if self._shift_pressed:
            self._execute_command("delete_row", self._delete_selected)
        else:
            self._execute_command("add_row", self._add_type)

    def _add_type(self) -> None:
        self._sync_detail_panel()
        if not self._session.add_type():
            return
        self._apply_filter(self._search_field.value or "")
        self._session.selected_row_idx = 0
        self._session.selected_row_indices = {0}
        self._render_page()
        self._load_detail_panel()
        self._update_detail_panel()
        self.control.update()

    def _delete_selected(self) -> None:
        if not self._session.selected_row_indices:
            return

        names = [
            self._session.rows[idx].values.get("name", "") or "(unnamed)"
            for idx in sorted(self._session.selected_row_indices)
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
        if not self._session.selected_row_indices:
            return

        self._sync_detail_panel()
        self._sync_page_back()

        if not self._session.delete_selected():
            return

        self._clear_selection()
        self._apply_filter(self._search_field.value or "")
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
        start = self._session.page_index * PAGE_SIZE
        actual_idx = (
            self._session.filtered[start + pool_slot]
            if start + pool_slot < len(self._session.filtered)
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
            if actual_idx in self._session.selected_row_indices:
                self._session.selected_row_indices.discard(actual_idx)
            else:
                self._session.selected_row_indices.add(actual_idx)
                self._session.selected_row_idx = actual_idx
            if len(self._session.selected_row_indices) == 1:
                self._load_detail_panel()
        else:
            self._session.selected_row_indices = {actual_idx}
            self._session.selected_row_idx = actual_idx
            self._load_detail_panel()
        self._update_detail_panel()
        self._render_page()
        self.control.update()
        self._refresh_commands()

    def _on_row_tap_down(self, e: object, pool_slot: int) -> None:
        self._mouse_down = True
        self._drag_start_slot = pool_slot

    def _on_row_hover(self, e: ft.ControlEvent, pool_slot: int) -> None:
        if not e.data:
            return
        if not self._shift_pressed or not self._mouse_down:
            return
        start = self._session.page_index * PAGE_SIZE

        if self._drag_start_slot is not None:
            start_idx = (
                self._session.filtered[start + self._drag_start_slot]
                if start + self._drag_start_slot < len(self._session.filtered)
                else -1
            )
            self._drag_start_slot = None
            if start_idx >= 0 and start_idx not in self._session.selected_row_indices:
                self._session.selected_row_indices.add(start_idx)
                self._session.selected_row_idx = start_idx
                self._render_page()
                self.control.update()

        actual_idx = (
            self._session.filtered[start + pool_slot]
            if start + pool_slot < len(self._session.filtered)
            else -1
        )
        if actual_idx < 0 or actual_idx in self._session.selected_row_indices:
            return
        self._sync_page_back()
        self._sync_detail_panel()
        self._session.selected_row_indices.add(actual_idx)
        self._session.selected_row_idx = actual_idx
        self._load_detail_panel()
        self._update_detail_panel()
        self._render_page()
        self.control.update()

    def _sync_detail_panel(self) -> None:
        if self._session.selected_row_idx is None or len(
            self._session.selected_row_indices
        ) > 1:
            return
        if not (
            hasattr(self._detail_panel, "_usage_chipset")
            and hasattr(self._detail_panel, "_value_chipset")
        ):
            return
        usage_chipset = getattr(self._detail_panel, "_usage_chipset", None)
        value_chipset = getattr(self._detail_panel, "_value_chipset", None)
        if not usage_chipset or not value_chipset:
            return
        usage = ", ".join(usage_chipset.get_values())
        value = ", ".join(value_chipset.get_values())
        row = self._session.rows[self._session.selected_row_idx]
        if row.values.get("usage") != usage or row.values.get("value") != value:
            self._session.record_undo()
            row.values["usage"] = usage
            row.values["value"] = value
            if usage or value:
                self._session.mark_dirty()

    def _update_detail_panel(self) -> None:
        if len(self._session.selected_row_indices) >= 2:
            self._batch_panel.show(
                f"Batch edit: {len(self._session.selected_row_indices)} rows selected",
                USAGES,
                VALUES_LIST,
                self._table_ctrl.flag_names,
            )
            self._detail_container.content = self._batch_panel.build()
        elif len(self._session.selected_row_indices) == 1:
            self._detail_container.content = self._detail_panel.build()
        else:
            self._detail_container.content = self._detail_placeholder

    def _load_detail_panel(self) -> None:
        if self._session.selected_row_idx is None:
            return
        row = self._session.rows[self._session.selected_row_idx]
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
        if key.startswith("flag:"):
            self._batch_apply_flag(key[5:])
        elif key in ("usage", "value"):
            self._batch_apply_chipset(key)
        else:
            self._batch_apply_field(key)

    def _batch_apply_field(self, field_key: str) -> None:
        self._sync_page_back()
        w = self._batch_fields.get(field_key)
        if w is None:
            return
        value = w.value or ""
        self._session.batch_apply_field(field_key, value)
        label = "Category" if field_key == "category" else field_key
        self._finish_batch_apply(label)

    def _batch_apply_chipset(self, column_key: str) -> None:
        self._sync_page_back()
        chipset = getattr(self._batch_panel, f"_{column_key}_chipset", None)
        parts = ", ".join(chipset.get_values()) if chipset else ""
        self._session.batch_apply_chipset(column_key, parts)
        self._finish_batch_apply(column_key.capitalize())

    def _batch_apply_flag(self, flag_name: str) -> None:
        self._sync_page_back()
        cb = self._batch_flag_checkboxes.get(flag_name)
        if cb is None:
            return
        value = "1" if cb.value else "0"
        self._session.batch_apply_flag(flag_name, value)
        self._finish_batch_apply(flag_name)

    def _finish_batch_apply(self, label: str) -> None:
        self._render_page()
        self._save_text.value = (
            f"{label} applied to {len(self._session.selected_row_indices)} rows"
        )
        self._save_text.color = ft.Colors.GREEN
        self.control.update()

    def _batch_save_field(self, field_key: str) -> None:
        self._batch_apply_field(field_key)

    def _clear_selection(self) -> None:
        self._mouse_down = False
        self._detail_panel.hide()
        self._detail_container.content = self._detail_placeholder
        self._session.clear_selection()

    def _prev_page(self, e: object) -> None:
        self._sync_detail_panel()
        self._sync_page_back()
        self._clear_selection()
        self._session.prev_page()
        self._render_page()
        self.control.update()

    def _next_page(self, e: object) -> None:
        self._sync_detail_panel()
        self._sync_page_back()
        self._clear_selection()
        self._session.next_page()
        self._render_page()
        self.control.update()

    def _apply_filter(self, query: str) -> None:
        self._session.apply_filter(
            query,
            case_sensitive=self._case_sensitive_checkbox.value,
            filters={
                key: menu.filter_value()
                for key, menu in self._filter_menus.items()
            },
        )

    def _on_search(self, e: object) -> None:
        self._sync_detail_panel()
        self._sync_page_back()
        query = (self._search_field.value or "").strip()
        self._apply_filter(query)
        self._session.reset_page()
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

    def _render_page(self) -> None:
        total = len(self._session.filtered)
        total_pages = self._session.total_pages()
        self._session.clamp()

        self._session.set_syncing(True)
        self._table_ctrl.render(
            self._session.rows,
            self._session.filtered,
            self._session.page_index,
            self._session.selected_row_indices,
        )
        self._session.set_syncing(False)

        self._page_info.value = (
            f"Page {self._session.page_index + 1}/{total_pages}  ({total} rows)"
        )
        self._prev_btn.disabled = self._session.page_index <= 0
        self._next_btn.disabled = self._session.page_index >= total_pages - 1
        self._refresh_button_states()

    def _sync_page_back(self) -> None:
        if self._session.path is None or not self._session.dirty:
            return
        self._session.record_undo()
        self._table_ctrl.sync_back(
            self._session.rows,
            self._session.filtered,
            self._session.page_index,
        )
        self._session.mark_clean()

    def _sync_widgets_to_rows(self) -> None:
        if self._session.path is None or not self._session.dirty:
            return
        self._table_ctrl.sync_back(
            self._session.rows,
            self._session.filtered,
            self._session.page_index,
        )
        self._session.mark_clean()

    def _on_undo(self, e: object) -> None:
        self._sync_widgets_to_rows()
        if self._session.undo():
            self._session.mark_dirty()
            self._clear_selection()
            self._session.refilter()
            self._render_page()
            self._refresh_button_states()
            self.control.update()

    def _on_redo(self, e: object) -> None:
        self._sync_widgets_to_rows()
        if self._session.redo():
            self._session.mark_dirty()
            self._clear_selection()
            self._session.refilter()
            self._render_page()
            self._refresh_button_states()
            self.control.update()

    def _refresh_button_states(self) -> None:
        self._undo_btn.disabled = not self._session.can_undo
        self._redo_btn.disabled = not self._session.can_redo
        self._undo_btn.update()
        self._redo_btn.update()
        self._refresh_commands()

    def update_funny_visibility(self) -> None:
        self._fun.update_funny_visibility([self._lucky_btn, self._stats_btn])

    def _try_update(self, ctrl: ft.Control) -> None:
        try:
            ctrl.update()
        except RuntimeError:
            pass

    def update_cat_icons(self) -> None:
        if not self._entertainment_service:
            return
        is_cat = self._fun.is_cat()
        self._save_btn.icon = self._fun.icon_for(ft.Icons.SAVE)
        self._multi_btn.icon = self._fun.icon_for(ft.Icons.SELECT_ALL)
        self._undo_btn.icon = self._fun.icon_for(ft.Icons.UNDO)
        self._redo_btn.icon = self._fun.icon_for(ft.Icons.REDO)
        self._lucky_btn.icon = self._fun.icon_for(ft.Icons.CASINO)
        self._stats_btn.icon = self._fun.icon_for(ft.Icons.BAR_CHART)
        self._search_field.icon = self._fun.icon_for(ft.Icons.SEARCH)
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
        for menu in self._filter_menus.values():
            menu.rebuild()
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
        self._fab.icon = self._fun.fab_icon(self._shift_pressed)
        self._try_update(self._fab)

    async def show_meow_popup(self) -> None:
        await self._fun.show_meow_popup()

    def _handle_post_save(self) -> None:
        self._fun.handle_post_save(self._session.rows)

    def _on_stats_click(self, e: object) -> None:
        self._fun.show_stats_dialog()

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

        target_indices = (
            self._session.selected_row_indices
            if self._session.selected_row_indices
            else set(range(len(self._session.rows)))
        )
        self._session.randomize(target_indices)

        self._render_page()
        self.control.update()

        phrase = self._fun.lucky_phrase()
        success_dialog = ft.AlertDialog(
            title=ft.Text("Randomization Complete!"),
            content=ft.Text(phrase, size=16, weight=ft.FontWeight.BOLD),
            actions=[ft.TextButton("OK", on_click=lambda _: self._page.pop_dialog())],
        )
        self._page.show_dialog(success_dialog)
        self._page.update()

    def save_file(self) -> None:
        if self._text_mode:
            self._save_text_file()
            return
        self._sync_detail_panel()
        self._sync_page_back()
        if self._session.path is not None:
            try:
                self._session.save()
                self._session.mark_clean()
            except Exception as ex:
                logger.error("Auto-save failed for %s: %s", self._session.path, ex)
            if self.on_saved:
                self.on_saved()

    def clear_cache(self, path: str) -> None:
        self.xml_repo.invalidate_cache(path)

    def clear(self) -> None:
        self._session.clear_all()
        self._text_mode = False
        self._text_container.visible = False
        self.control.content = self._keyboard_listener
        self._table_ctrl.clear()
        self._save_text.value = ""
        for menu in self._filter_menus.values():
            menu.clear()
        self.control.visible = False
        self._detail_panel.hide()
        self._detail_container.content = self._detail_placeholder
        self._batch_panel.hide()

        if self._tip_task is not None and not self._tip_task.done():
            self._tip_task.cancel()
        self._tip_task = None
        logger.debug("FileDisplay cleared")