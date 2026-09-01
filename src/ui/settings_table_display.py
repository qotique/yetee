from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor

import flet as ft

from controllers.table_controller import PAGE_SIZE, TableController
from commands.registry import CommandRegistry
from models.custom_entities import get_columns, get_renderer
from core.exceptions import AccessError, ParseError
from models.field_def import FieldDef
from models.row_data import RowData
from repository.settings_repository import JsonSettingsRepository, XmlSettingsRepository

logger = logging.getLogger(__name__)

RENDERER_XML = "xml"
RENDERER_JSON = "json"
RENDERER_TXT = "txt"

MAX_UNDO = 50

_executor = ThreadPoolExecutor(max_workers=2)


def _snapshot_rows(rows: list[RowData]) -> list[dict[str, str]]:
    return [dict(r.values) for r in rows]


def _restore_rows(snapshot: list[dict[str, str]], rows: list[RowData]) -> None:
    for row, values in zip(rows, snapshot):
        row.values.clear()
        row.values.update(values)


class SettingsTableDisplay:
    """Generic display for custom entities.

    Renders .xml / .json files as an editable settings table (auto-detected
    columns, optionally overridden by a schema in ``models/custom_entities.py``) and
    .txt files as a raw text editor. Exposes the same public surface as
    ``FileDisplay`` so it can be used as an ``_EntityConfig.display``.
    """

    def __init__(
        self,
        page: ft.Page,
        xml_repo: XmlSettingsRepository | None = None,
        json_repo: JsonSettingsRepository | None = None,
        page_size: int = PAGE_SIZE,
        commands: CommandRegistry | None = None,
    ):
        self._page = page
        self._xml_repo = xml_repo or XmlSettingsRepository()
        self._json_repo = json_repo or JsonSettingsRepository()
        self._page_size = page_size
        self._commands = commands

        self.on_saved: Callable[[], None] | None = None

        self._path: str | None = None
        self._entity: str = ""
        self._renderer: str = RENDERER_XML
        self._field_defs: list[FieldDef] = []
        self._rows: list[RowData] = []
        self._page_idx: int = 0
        self._dirty: bool = False
        self._undo_stack: list[list[dict[str, str]]] = []
        self._redo_stack: list[list[dict[str, str]]] = []
        self._parsed_cache: dict[str, tuple[list[FieldDef], list[RowData]]] = {}

        self._table_ctrl = TableController(page)
        self._table_widget = self._table_ctrl.get_table_widget()
        self._table_slot = ft.Container(expand=True, content=self._table_widget)

        self._text_editor = ft.TextField(
            multiline=True,
            min_lines=1,
            expand=True,
            dense=True,
            border=ft.InputBorder.NONE,
            on_change=self._on_text_change,
        )
        self._text_container = ft.Container(
            visible=False,
            expand=True,
            content=ft.Container(
                content=self._text_editor,
                border=ft.border.Border(
                    top=ft.border.BorderSide(1, ft.Colors.OUTLINE_VARIANT),
                    bottom=ft.border.BorderSide(1, ft.Colors.OUTLINE_VARIANT),
                    left=ft.border.BorderSide(1, ft.Colors.OUTLINE_VARIANT),
                    right=ft.border.BorderSide(1, ft.Colors.OUTLINE_VARIANT),
                ),
                border_radius=8,
                padding=10,
                expand=True,
            ),
        )

        self._core = ft.Column(
            [self._table_slot, self._text_container],
            expand=True,
            spacing=0,
        )
        self.control = ft.Container(visible=False, expand=True, content=self._core)

        self._status = ft.Text("", size=12, selectable=True)
        self._page_info = ft.Text("", size=12)
        self._save_btn = ft.Button(
            "Save",
            icon=ft.Icons.SAVE,
            on_click=self._bind("save", self.save_current),
        )
        self._undo_btn = ft.IconButton(
            icon=ft.Icons.UNDO, on_click=self._bind("undo", self._on_undo)
        )
        self._redo_btn = ft.IconButton(
            icon=ft.Icons.REDO, on_click=self._bind("redo", self._on_redo)
        )
        self._prev_btn = ft.Button(
            "Prev", on_click=self._bind("prev_page", self._prev_page)
        )
        self._next_btn = ft.Button(
            "Next", on_click=self._bind("next_page", self._next_page)
        )
        self._search_field = ft.TextField(
            label="Search",
            icon=ft.Icons.SEARCH,
            dense=True,
            text_size=12,
            width=250,
            on_change=self._on_search,
        )

        self.button_row = ft.Row(
            [
                self._save_btn,
                self._undo_btn,
                self._redo_btn,
                ft.Divider(),
                self._status,
                ft.Divider(),
                self._prev_btn,
                self._page_info,
                self._next_btn,
                self._search_field,
            ],
            alignment=ft.MainAxisAlignment.START,
        )

    def _bind(
        self,
        command_id: str,
        fallback: Callable[[object], None],
    ) -> Callable[[object], None]:
        commands = self._commands
        if commands is not None:
            return lambda _e: commands.invoke(command_id)
        return fallback

    def _refresh_commands(self) -> None:
        if self._commands is not None:
            self._commands.refresh()

    def set_entity(self, entity: str) -> None:
        self._entity = entity

    @property
    def is_dirty(self) -> bool:
        return self._dirty

    def _set_status(self, message: str) -> None:
        self._status.value = message
        self._status.update()

    def load_file(self, path: str) -> None:
        self._path = path
        renderer = get_renderer(self._entity, path)
        self._renderer = renderer
        if renderer == RENDERER_TXT:
            self._load_text_file(path)
        else:
            defs, rows = self._parse_table_file(path, renderer)
            self._apply_table_file(defs, rows)

    async def load_file_async(
        self,
        path: str,
        cancel_check: Callable[[], bool] | None = None,
    ) -> None:
        self._path = path
        renderer = get_renderer(self._entity, path)
        self._renderer = renderer
        if renderer == RENDERER_TXT:
            self._load_text_file(path)
            return
        loop = asyncio.get_running_loop()

        defs, rows = await loop.run_in_executor(
            _executor, self._parse_table_file, path, renderer
        )
        if cancel_check and cancel_check():
            return
        self._apply_table_file(defs, rows)

    def _parse_table_file(
        self, path: str, renderer: str
    ) -> tuple[list[FieldDef], list[RowData]]:
        cached = self._parsed_cache.get(path)
        if cached is not None:
            return cached
        if renderer == RENDERER_JSON:
            declared = get_columns(self._entity, path)
            result = self._json_repo.parse_file(path, declared or None)
        else:
            result = self._xml_repo.parse_file(path)
        self._parsed_cache[path] = result
        return result

    async def preload_cached(
        self,
        paths: list[str],
        on_progress: Callable[[int, int], None] | None = None,
        cancel_check: Callable[[], bool] | None = None,
    ) -> None:
        loop = asyncio.get_running_loop()
        for done, path in enumerate(paths, start=1):
            if cancel_check and cancel_check():
                return
            if path in self._parsed_cache:
                if on_progress:
                    on_progress(done, len(paths))
                continue
            renderer = get_renderer(self._entity, path)
            if renderer == RENDERER_TXT:
                if on_progress:
                    on_progress(done, len(paths))
                continue
            try:
                await loop.run_in_executor(
                    _executor, self._parse_table_file, path, renderer
                )
            except (ParseError, AccessError):
                logger.warning(
                    "Skipped unparsable profile file during preload: %s", path
                )
            if on_progress:
                on_progress(done, len(paths))

    def _apply_table_file(self, defs: list[FieldDef], rows: list[RowData]) -> None:
        declared = list(get_columns(self._entity, self._path or ""))
        if declared:
            declared_keys = {fd.key for fd in declared}
            extras = [fd for fd in (defs or []) if fd.key not in declared_keys]
            self._field_defs = declared + extras
        else:
            self._field_defs = defs or []
        self._rows = rows
        self._page_idx = 0
        self._dirty = False
        self._undo_stack = []
        self._redo_stack = []
        self._table_ctrl.init_table(self._field_defs)
        self._table_ctrl.set_callbacks(on_field_change=self._on_table_change)
        self._show_text(False)
        self.control.visible = True
        self._render_table()
        self.control.update()

    def _load_text_file(self, path: str) -> None:
        try:
            with open(path, encoding="utf-8", errors="replace") as fh:
                content = fh.read()
        except OSError as exc:
            logger.warning("Could not read text file %s: %s", path, exc)
            self._status.value = f"Error reading file: {exc}"
            self._status.update()
            return
        self._text_editor.value = content
        self._dirty = False
        self._undo_stack = []
        self._redo_stack = []
        self._show_text(True)
        self.control.visible = True
        self.control.update()

    def _show_text(self, visible: bool) -> None:
        self._table_slot.visible = not visible
        self._text_container.visible = visible

    def _filtered(self) -> list[int]:
        query = (self._search_field.value or "").strip().lower()
        if not query:
            return list(range(len(self._rows)))
        parts = [p.strip() for p in query.split("|") if p.strip()]
        return [
            i
            for i, row in enumerate(self._rows)
            if any(
                p in " ".join(f"{k}={v}" for k, v in row.values.items()).lower()
                for p in parts
            )
        ]

    def _render_table(self) -> None:
        filtered = self._filtered()
        total = len(filtered)
        if total and self._page_idx * self._page_size >= total:
            self._page_idx = max(0, (total - 1) // self._page_size)
        self._table_ctrl.render(self._rows, filtered, self._page_idx, set())
        start = self._page_idx * self._page_size
        end = min(start + self._page_size, total)
        self._page_info.value = f"{start + 1}-{end}" if total else "0-0"
        self._page_info.update()

    def _on_text_change(self, e: object) -> None:
        self._dirty = True

    def _on_search(self, e: object) -> None:
        self._page_idx = 0
        self._render_table()

    def _prev_page(self, e: object) -> None:
        if self._page_idx > 0:
            self._page_idx -= 1
            self._render_table()
            self._refresh_commands()

    def _next_page(self, e: object) -> None:
        total = len(self._filtered())
        if (self._page_idx + 1) * self._page_size < total:
            self._page_idx += 1
            self._render_table()
            self._refresh_commands()

    def _on_table_change(self, e: object) -> None:
        current = _snapshot_rows(self._rows)
        if self._undo_stack and self._undo_stack[-1] == current:
            return
        self._undo_stack.append(current)
        if len(self._undo_stack) > MAX_UNDO:
            self._undo_stack.pop(0)
        self._redo_stack = []
        self._dirty = True
        self._refresh_commands()

    def _on_undo(self, e: object) -> None:
        if not self._undo_stack:
            return
        snapshot = self._undo_stack.pop()
        self._redo_stack.append(_snapshot_rows(self._rows))
        _restore_rows(snapshot, self._rows)
        self._dirty = True
        self._render_table()
        self._refresh_commands()

    def _on_redo(self, e: object) -> None:
        if not self._redo_stack:
            return
        snapshot = self._redo_stack.pop()
        self._undo_stack.append(_snapshot_rows(self._rows))
        _restore_rows(snapshot, self._rows)
        self._dirty = True
        self._render_table()
        self._refresh_commands()

    def _sync_back_rows(self) -> None:
        self._table_ctrl.sync_back(self._rows, self._filtered(), self._page_idx)

    def save_current(self, e: object = None) -> None:
        self._save_current_file()

    def save_file(self) -> None:
        self._save_current_file()

    def save_async(self) -> None:
        self._save_current_file()

    def _save_current_file(self) -> None:
        if self._path is None:
            return
        if self._renderer == RENDERER_TXT:
            self._save_text_file()
        else:
            self._sync_back_rows()
            self._save_table_file()

    def _save_text_file(self) -> None:
        target = self._path
        if target is None:
            return
        try:
            with open(target, "w", encoding="utf-8") as fh:
                fh.write(self._text_editor.value or "")
            self._dirty = False
            self._status.value = "Saved"
            self._status.update()
            if self.on_saved:
                self.on_saved()
        except OSError as exc:
            logger.error("Failed to save text file %s: %s", target, exc)
            self._status.value = f"Error saving: {exc}"
            self._status.update()

    def _save_table_file(self) -> None:
        target = self._path
        if target is None:
            return
        try:
            if self._renderer == RENDERER_JSON:
                self._json_repo.save(target, self._rows)
            else:
                self._xml_repo.save(target, self._rows)
            self._dirty = False
            self._status.value = "Saved"
            self._status.update()
            if self.on_saved:
                self.on_saved()
        except Exception as exc:
            logger.error("Save settings failed for %s: %s", target, exc)
            self._status.value = f"Error saving: {exc}"
            self._status.update()

    def clear(self) -> None:
        self._path = None
        self._renderer = RENDERER_XML
        self._field_defs = []
        self._rows = []
        self._page_idx = 0
        self._dirty = False
        self._undo_stack = []
        self._redo_stack = []
        self._parsed_cache = {}
        self._text_editor.value = ""
        self._search_field.value = ""
        self._show_text(False)
        self._table_ctrl.clear()
        self.control.visible = False

    def clear_cache(self, path: str) -> None:
        self._parsed_cache.pop(path, None)
        self._xml_repo.invalidate_cache(path)
        self._json_repo.invalidate_cache(path)

    def undo(self, e: object = None) -> None:
        self._on_undo(None)

    def redo(self, e: object = None) -> None:
        self._on_redo(None)

    def prev_page(self, e: object = None) -> None:
        self._prev_page(None)

    def next_page(self, e: object = None) -> None:
        self._next_page(None)

    @property
    def can_undo(self) -> bool:
        return bool(self._undo_stack)

    @property
    def can_redo(self) -> bool:
        return bool(self._redo_stack)

    @property
    def can_add(self) -> bool:
        return False

    @property
    def can_delete(self) -> bool:
        return False

    @property
    def can_prev(self) -> bool:
        return self._page_idx > 0

    @property
    def can_next(self) -> bool:
        return (self._page_idx + 1) * self._page_size < len(self._filtered())
