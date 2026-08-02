from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from models.row_data import RowData

if TYPE_CHECKING:
    from lxml import etree as ET


@dataclass
class RowSnapshot:
    values: dict[str, str]
    flags: dict[str, str]
    elem: ET.Element | None = None


class UndoManager:
    def __init__(self, max_history: int = 50):
        self._undo_stack: list[list[RowSnapshot]] = []
        self._redo_stack: list[list[RowSnapshot]] = []
        self._max = max_history

    def take_snapshot(self, rows: list[RowData]) -> list[RowSnapshot]:
        return [
            RowSnapshot(
                values=dict(r.values),
                flags=dict(r.flags),
                elem=r.elem,
            )
            for r in rows
        ]

    def record(self, snapshot: list[RowSnapshot]) -> None:
        self._undo_stack.append(snapshot)
        self._redo_stack.clear()
        if len(self._undo_stack) > self._max:
            self._undo_stack.pop(0)

    def undo(self, rows: list[RowData], root: ET.Element | None = None) -> bool:
        if not self._undo_stack:
            return False
        snapshot = self._undo_stack.pop()
        self._redo_stack.append(self.take_snapshot(rows))
        self._apply(rows, snapshot, root)
        return True

    def redo(self, rows: list[RowData], root: ET.Element | None = None) -> bool:
        if not self._redo_stack:
            return False
        snapshot = self._redo_stack.pop()
        self._undo_stack.append(self.take_snapshot(rows))
        self._apply(rows, snapshot, root)
        return True

    def _apply(
        self,
        rows: list[RowData],
        snapshot: list[RowSnapshot],
        root: ET.Element | None = None,
    ) -> None:
        if len(rows) != len(snapshot):
            snapshot_elems = {id(s.elem) for s in snapshot if s.elem is not None}

            i = 0
            while i < len(rows):
                row = rows[i]
                if row.elem is not None and id(row.elem) not in snapshot_elems:
                    if root is not None and row.elem.getparent() == root:
                        root.remove(row.elem)
                    rows.pop(i)
                else:
                    i += 1

            current_elems = {id(r.elem) for r in rows if r.elem is not None}
            for si, s in enumerate(snapshot):
                if s.elem is not None and id(s.elem) not in current_elems:
                    new_row = RowData(
                        values=dict(s.values),
                        flags=dict(s.flags),
                        elem=s.elem,
                    )
                    if root is not None and s.elem.getparent() != root:
                        root.append(s.elem)
                    rows.insert(si, new_row)
                    current_elems.add(id(s.elem))

        for r, s in zip(rows, snapshot):
            r.values = dict(s.values)
            r.flags = dict(s.flags)

    def clear(self) -> None:
        self._undo_stack.clear()
        self._redo_stack.clear()

    @property
    def can_undo(self) -> bool:
        return len(self._undo_stack) > 0

    @property
    def can_redo(self) -> bool:
        return len(self._redo_stack) > 0
