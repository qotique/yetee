from __future__ import annotations

import logging
from collections.abc import Iterable, Mapping

from lxml import etree as ET

from controllers.commands import RandomizeCommand, SaveCommand
from controllers.dirty_state_manager import DirtyStateManager
from controllers.pagination_controller import PaginationController
from controllers.search_controller import SearchController
from controllers.table_controller import DEFAULT_FLAG_NAMES, PAGE_SIZE
from models.field_def import STATIC_FIELD_DEFS
from models.row_data import RowData
from models.undo_manager import UndoManager
from core.protocols import IXmlRepository
from repository.file_cache import FileCache

logger = logging.getLogger(__name__)


class FileSession:
    def __init__(
        self,
        xml_repo: IXmlRepository,
        cache: FileCache,
        pagination: PaginationController | None = None,
        search: SearchController | None = None,
        dirty_state: DirtyStateManager | None = None,
        undo_mgr: UndoManager | None = None,
    ) -> None:
        self.xml_repo = xml_repo
        self.cache = cache
        self._pagination = pagination or PaginationController(PAGE_SIZE)
        self._search = search or SearchController()
        self._dirty_state = dirty_state or DirtyStateManager()
        self._undo_mgr = undo_mgr or UndoManager()

        self.path: str | None = None
        self.rows: list[RowData] = []
        self.filtered: list[int] = []
        self.selected_row_idx: int | None = None
        self.selected_row_indices: set[int] = set()

    @property
    def dirty(self) -> bool:
        return self._dirty_state.is_dirty

    @property
    def page_index(self) -> int:
        return self._pagination.page_index

    @page_index.setter
    def page_index(self, value: int) -> None:
        self._pagination.page_index = value

    @property
    def can_undo(self) -> bool:
        return self._undo_mgr.can_undo

    @property
    def can_redo(self) -> bool:
        return self._undo_mgr.can_redo

    def load_setup(self, path: str) -> None:
        self.path = path
        self.rows = []
        self.filtered = []
        self.selected_row_idx = None
        self.selected_row_indices.clear()
        self._pagination.reset()
        self._search.reset()
        self._dirty_state.reset()
        self._undo_mgr.clear()

    def clear_all(self) -> None:
        self.path = None
        self.rows = []
        self.filtered = []
        self.selected_row_idx = None
        self.selected_row_indices.clear()
        self._pagination.reset()
        self._search.reset()
        self._dirty_state.reset()
        self._undo_mgr.clear()

    def record_undo(self) -> None:
        self._undo_mgr.record(self._undo_mgr.take_snapshot(self.rows))

    def reset_transient(self) -> None:
        self._undo_mgr.clear()
        self._dirty_state.reset()

    def mark_dirty(self) -> None:
        self._dirty_state.mark_dirty()

    def mark_clean(self) -> None:
        self._dirty_state.mark_clean()

    def set_syncing(self, value: bool) -> None:
        self._dirty_state.set_syncing(value)

    def apply_filter(
        self,
        query: str,
        case_sensitive: bool,
        filters: Mapping[str, str],
    ) -> None:
        self._search.set_search(query, case_sensitive=case_sensitive)
        self._search.set_filters(filters)
        self.filtered = self._search.filter_rows(self.rows)

    def refilter(self) -> None:
        self.filtered = self._search.filter_rows(self.rows)

    def clear_selection(self) -> None:
        self.selected_row_idx = None
        self.selected_row_indices.clear()

    def total_pages(self) -> int:
        return self._pagination.total_pages(len(self.filtered))

    def prev_page(self) -> None:
        self._pagination.prev_page(len(self.filtered))

    def next_page(self) -> None:
        self._pagination.next_page(len(self.filtered))

    def reset_page(self) -> None:
        self._pagination.reset()

    def clamp(self) -> None:
        self._pagination.clamp(len(self.filtered))

    def _get_root(self) -> ET.Element | None:
        if self.path is None:
            return None
        tree = self.cache.get_tree(self.path)
        return tree.getroot() if tree is not None else None

    def add_type(self) -> bool:
        root = self._get_root()
        if root is None:
            return False
        new_elem = ET.SubElement(root, "type")
        new_elem.set("name", "")
        new_row = RowData(values={}, flags={}, elem=new_elem)
        for fd in STATIC_FIELD_DEFS:
            new_row.values[fd.key] = "" if fd.key == "name" else "0"
        for fn in DEFAULT_FLAG_NAMES:
            new_row.flags[fn] = "0"
        self.record_undo()
        self.rows.insert(0, new_row)
        self._pagination.reset()
        self.mark_dirty()
        return True

    def delete_selected(self) -> bool:
        if not self.selected_row_indices:
            return False
        root = self._get_root()
        if root is None:
            return False
        self.record_undo()
        for idx in sorted(self.selected_row_indices, reverse=True):
            row = self.rows[idx]
            if row.elem is not None:
                root.remove(row.elem)
            del self.rows[idx]
        self.clear_selection()
        self._pagination.clamp(len(self.filtered))
        self.mark_dirty()
        return True

    def randomize(self, indices: Iterable[int]) -> None:
        self.record_undo()
        RandomizeCommand(self.rows, indices).execute()
        self.refilter()
        self.mark_dirty()

    def batch_apply_field(self, field_key: str, value: str) -> None:
        self.record_undo()
        for idx in self.selected_row_indices:
            self.rows[idx].values[field_key] = value
        self.mark_dirty()

    def batch_apply_chipset(self, column_key: str, parts: str) -> None:
        self.record_undo()
        for idx in self.selected_row_indices:
            self.rows[idx].values[column_key] = parts
        self.mark_dirty()

    def batch_apply_flag(self, flag_name: str, value: str) -> None:
        self.record_undo()
        for idx in self.selected_row_indices:
            self.rows[idx].flags[flag_name] = value
        self.mark_dirty()

    def undo(self) -> bool:
        return self._undo_mgr.undo(self.rows, root=self._get_root())

    def redo(self) -> bool:
        return self._undo_mgr.redo(self.rows, root=self._get_root())

    def save(self) -> None:
        if self.path is None:
            return
        SaveCommand(self.xml_repo, self.path, self.rows).execute()

    async def save_async(self) -> None:
        if self.path is None:
            return
        await SaveCommand(self.xml_repo, self.path, self.rows).execute_async()