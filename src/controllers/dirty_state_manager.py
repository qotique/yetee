from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class DirtyStateManager:
    def __init__(self) -> None:
        self._dirty: bool = False
        self._syncing: bool = False

    @property
    def is_dirty(self) -> bool:
        return self._dirty

    def mark_dirty(self) -> None:
        if not self._syncing:
            self._dirty = True
            logger.debug("Dirty state: marked dirty")

    def mark_clean(self) -> None:
        self._dirty = False
        logger.debug("Dirty state: marked clean")

    @property
    def is_syncing(self) -> bool:
        return self._syncing

    def set_syncing(self, value: bool) -> None:
        self._syncing = value

    def reset(self) -> None:
        self._dirty = False
        self._syncing = False
