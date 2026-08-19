from __future__ import annotations

import logging
from collections.abc import Mapping

from models.row_data import RowData

logger = logging.getLogger(__name__)

EMPTY_CATEGORY_MARKER = "__empty__"
EMPTY_USAGE_MARKER = "__usage_empty__"
EMPTY_VALUE_MARKER = "__value_empty__"

EMPTY_MARKERS: dict[str, str] = {
    "category": EMPTY_CATEGORY_MARKER,
    "usage": EMPTY_USAGE_MARKER,
    "value": EMPTY_VALUE_MARKER,
}


class SearchController:
    def __init__(self) -> None:
        self._search_query: str = ""
        self._filters: dict[str, str] = {}
        self._case_sensitive: bool = False

    @property
    def query(self) -> str:
        return self._search_query

    @property
    def case_sensitive(self) -> bool:
        return self._case_sensitive

    @property
    def filters(self) -> dict[str, str]:
        return dict(self._filters)

    def set_search(self, value: str, case_sensitive: bool = False) -> None:
        self._case_sensitive = bool(case_sensitive)
        query = (value or "").strip()
        self._search_query = query if self._case_sensitive else query.lower()

    def set_filters(self, filters: Mapping[str, str]) -> None:
        self._filters = {
            key: (value or "").strip().lower() for key, value in filters.items()
        }

    def _normalize(self, text: str) -> str:
        return text if self._case_sensitive else text.lower()

    def _row_matches_filter(self, row: RowData, key: str, parts: list[str]) -> bool:
        marker = EMPTY_MARKERS.get(key)
        value = row.values.get(key, "")
        return any(
            value.strip() == ""
            if marker is not None and p == marker
            else p in value.lower()
            for p in parts
        )

    def filter_rows(self, rows: list[RowData]) -> list[int]:
        search_parts = (
            [q.strip() for q in self._search_query.split("|") if q.strip()]
            if self._search_query
            else []
        )
        parsed: list[tuple[str, list[str]]] = []
        for key, filter_value in self._filters.items():
            parts = [
                p.strip().lower() for p in filter_value.split("|") if p.strip()
            ]
            if parts:
                parsed.append((key, parts))

        result = [
            i
            for i, row in enumerate(rows)
            if (
                not search_parts
                or any(
                    p in self._normalize(row.values.get("name", ""))
                    for p in search_parts
                )
            )
            and all(
                self._row_matches_filter(row, key, parts) for key, parts in parsed
            )
        ]

        logger.debug(
            "Filter applied: search=%r filters=%r -> %d/%d rows",
            self._search_query,
            self._filters,
            len(result),
            len(rows),
        )
        return result

    def reset(self) -> None:
        self._search_query = ""
        self._filters = {}