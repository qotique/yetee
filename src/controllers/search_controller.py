from __future__ import annotations

import logging

from models.row_data import RowData

logger = logging.getLogger(__name__)


class SearchController:
    def __init__(self) -> None:
        self._search_query: str = ""
        self._category_filter: str = ""
        self._usage_filter: str = ""
        self._value_filter: str = ""

    @property
    def query(self) -> str:
        return self._search_query

    def set_search(self, value: str) -> None:
        self._search_query = (value or "").strip().lower()

    def set_filters(
        self,
        category: str = "",
        usage: str = "",
        value: str = "",
    ) -> None:
        self._category_filter = (category or "").strip().lower()
        self._usage_filter = (usage or "").strip().lower()
        self._value_filter = (value or "").strip().lower()

    def filter_rows(self, rows: list[RowData]) -> list[int]:
        search_parts = [q.strip() for q in self._search_query.split("|") if q.strip()] if self._search_query else []
        cat_parts = [p.strip().lower() for p in self._category_filter.split("|") if p.strip()] if self._category_filter else []
        usage_parts = [p.strip().lower() for p in self._usage_filter.split("|") if p.strip()] if self._usage_filter else []
        value_parts = [p.strip().lower() for p in self._value_filter.split("|") if p.strip()] if self._value_filter else []

        result = [
            i for i, row in enumerate(rows)
            if (not search_parts or any(p in row.values.get("name", "").lower() for p in search_parts))
            and (not cat_parts or any(p in row.values.get("category", "").lower() for p in cat_parts))
            and (not usage_parts or any(p in row.values.get("usage", "").lower() for p in usage_parts))
            and (not value_parts or any(p in row.values.get("value", "").lower() for p in value_parts))
        ]

        logger.debug("Filter applied: search=%r cat=%r usage=%r value=%r -> %d/%d rows",
                     self._search_query, self._category_filter, self._usage_filter, self._value_filter,
                     len(result), len(rows))
        return result

    def reset(self) -> None:
        self._search_query = ""
        self._category_filter = ""
        self._usage_filter = ""
        self._value_filter = ""
