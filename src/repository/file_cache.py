from __future__ import annotations

from lxml import etree as ET

from models.row_data import RowData


class FileCache:
    def __init__(self):
        self._cache: dict[str, list[RowData]] = {}
        self._cache_trees: dict[str, ET.ElementTree] = {}

    def get_rows(self, path: str) -> list[RowData] | None:
        return self._cache.get(path)

    def set_rows(self, path: str, rows: list[RowData]):
        self._cache[path] = rows

    def get_tree(self, path: str) -> ET.ElementTree | None:
        return self._cache_trees.get(path)

    def set_tree(self, path: str, tree: ET.ElementTree):
        self._cache_trees[path] = tree

    def invalidate(self, path: str):
        self._cache.pop(path, None)
        self._cache_trees.pop(path, None)

    def clear_all(self):
        self._cache.clear()
        self._cache_trees.clear()
