from dataclasses import dataclass

from models.row_data import RowData


@dataclass
class RowSnapshot:
    values: dict[str, str]
    flags: dict[str, str]


class UndoManager:
    def __init__(self, max_history: int = 50):
        self._undo_stack: list[list[RowSnapshot]] = []
        self._redo_stack: list[list[RowSnapshot]] = []
        self._max = max_history

    def take_snapshot(self, rows: list[RowData]) -> list[RowSnapshot]:
        return [RowSnapshot(values=dict(r.values), flags=dict(r.flags)) for r in rows]

    def record(self, snapshot: list[RowSnapshot]) -> None:
        self._undo_stack.append(snapshot)
        self._redo_stack.clear()
        if len(self._undo_stack) > self._max:
            self._undo_stack.pop(0)

    def undo(self, rows: list[RowData]) -> bool:
        if not self._undo_stack:
            return False
        snapshot = self._undo_stack.pop()
        self._redo_stack.append(self.take_snapshot(rows))
        self._apply(rows, snapshot)
        return True

    def redo(self, rows: list[RowData]) -> bool:
        if not self._redo_stack:
            return False
        snapshot = self._redo_stack.pop()
        self._undo_stack.append(self.take_snapshot(rows))
        self._apply(rows, snapshot)
        return True

    def _apply(self, rows: list[RowData], snapshot: list[RowSnapshot]) -> None:
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



