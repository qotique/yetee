from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class PaginationController:
    def __init__(self, page_size: int = 50):
        self._page_size = page_size
        self._page_idx: int = 0

    @property
    def page_index(self) -> int:
        return self._page_idx

    @page_index.setter
    def page_index(self, value: int) -> None:
        self._page_idx = max(0, value)

    @property
    def page_size(self) -> int:
        return self._page_size

    def total_pages(self, total_items: int) -> int:
        return max(1, (total_items + self._page_size - 1) // self._page_size)

    def visible_range(self, total_items: int) -> tuple[int, int]:
        start = self._page_idx * self._page_size
        end = min(start + self._page_size, total_items)
        return (start, end)

    def clamp(self, total_items: int) -> None:
        total = self.total_pages(total_items)
        if self._page_idx >= total:
            self._page_idx = max(0, total - 1)

    def next_page(self, total_items: int) -> bool:
        if self._page_idx < self.total_pages(total_items) - 1:
            self._page_idx += 1
            logger.debug("Pagination: next page -> %d", self._page_idx)
            return True
        return False

    def prev_page(self, total_items: int) -> bool:
        if self._page_idx > 0:
            self._page_idx -= 1
            logger.debug("Pagination: prev page -> %d", self._page_idx)
            return True
        return False

    def reset(self) -> None:
        self._page_idx = 0
