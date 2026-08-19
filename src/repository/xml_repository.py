from __future__ import annotations

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor

from lxml import etree as ET

from core.exceptions import ParseError, AccessError
from models.field_def import STATIC_FIELD_DEFS
from models.row_data import RowData
from repository.file_cache import FileCache
from repository.xml_utils import elem_text, set_elem_text

logger = logging.getLogger(__name__)

_executor = ThreadPoolExecutor(max_workers=2)


def _names_to_str(elems: list[ET.Element]) -> str:
    names = [e.get("name", "") for e in elems if e.get("name")]
    return ", ".join(names)


class XmlRepository:
    def __init__(self, cache: FileCache | None = None):
        self._cache = cache or FileCache()

    def parse_file(self, path: str) -> list[RowData]:
        cached = self._cache.get_rows(path)
        if cached is not None:
            logger.debug("Cache hit for %s", path)
            return cached

        logger.info("Parsing file: %s", path)
        try:
            tree = ET.parse(path)
        except ET.ParseError as ex:
            logger.error("Failed to parse XML %s: %s", path, ex)
            raise ParseError(f"Failed to parse {path}: {ex}") from ex
        except FileNotFoundError as ex:
            logger.error("File not found: %s", path)
            raise AccessError(f"File not found: {path}") from ex
        except Exception as ex:
            logger.error("Error reading file %s: %s", path, ex)
            raise AccessError(f"Cannot read {path}: {ex}") from ex

        self._cache.set_tree(path, tree)
        root = tree.getroot()
        rows = [self._build_row(t) for t in root.findall("type")]
        self._cache.set_rows(path, rows)
        logger.debug("Parsed %d rows from %s", len(rows), path)
        return rows

    async def parse_file_async(self, path: str) -> list[RowData]:
        cached = self._cache.get_rows(path)
        if cached is not None:
            logger.debug("Cache hit for %s", path)
            return cached
        logger.info("Parsing file (async): %s", path)
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(_executor, self._parse_file_sync, path)

    def _parse_file_sync(self, path: str) -> list[RowData]:
        return self.parse_file(path)

    def save(self, path: str, rows: list[RowData]) -> None:
        logger.info("Saving %d rows to %s", len(rows), path)
        tree = self._cache.get_tree(path)
        if tree is None:
            logger.warning("No cached tree for %s, re-parsing", path)
            try:
                tree = ET.parse(path)
                self._cache.set_tree(path, tree)
            except Exception as ex:
                raise ParseError(f"Cannot re-parse {path}: {ex}") from ex

        if tree is None:
            raise ParseError(f"No element tree available for {path}")

        for row_data in rows:
            elem = row_data.elem
            assert elem is not None
            elem.set("name", row_data.values.get("name", ""))
            set_elem_text(elem, "nominal", row_data.values.get("nominal", ""))
            set_elem_text(elem, "lifetime", row_data.values.get("lifetime", ""))
            set_elem_text(elem, "restock", row_data.values.get("restock", ""))
            set_elem_text(elem, "min", row_data.values.get("min", ""))
            set_elem_text(elem, "quantmin", row_data.values.get("quantmin", ""))
            set_elem_text(elem, "quantmax", row_data.values.get("quantmax", ""))
            set_elem_text(elem, "cost", row_data.values.get("cost", ""))
            self._update_flags(elem, row_data.flags)
            self._update_named_elements(
                elem, "category", row_data.values.get("category", "")
            )
            self._update_named_elements(elem, "usage", row_data.values.get("usage", ""))
            self._update_named_elements(elem, "value", row_data.values.get("value", ""))

        try:
            ET.indent(tree, space="\t")
            tree.write(path, encoding="UTF-8", xml_declaration=True)
            logger.info("Saved %s successfully", path)
        except Exception as ex:
            logger.error("Failed to save %s: %s", path, ex)
            raise AccessError(f"Failed to save {path}: {ex}") from ex

    async def save_async(self, path: str, rows: list[RowData]) -> None:
        logger.info("Saving (async) %d rows to %s", len(rows), path)
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(_executor, self._save_sync, path, rows)

    def _save_sync(self, path: str, rows: list[RowData]) -> None:
        self.save(path, rows)

    def invalidate_cache(self, path: str) -> None:
        self._cache.invalidate(path)
        logger.debug("Invalidated cache for %s", path)

    def _build_row(self, type_elem: ET.Element) -> RowData:
        flags_elem = type_elem.find("flags")
        values: dict[str, str] = {}
        for fd in STATIC_FIELD_DEFS:
            if fd.key == "name":
                values[fd.key] = type_elem.get("name", "")
            else:
                values[fd.key] = elem_text(type_elem, fd.key)

        cat_elem = type_elem.find("category")
        values["category"] = cat_elem.get("name", "") if cat_elem is not None else ""
        values["usage"] = _names_to_str(type_elem.findall("usage"))
        values["value"] = _names_to_str(type_elem.findall("value"))

        return RowData(
            values=values,
            flags={k: v for k, v in flags_elem.attrib.items()}
            if flags_elem is not None
            else {},
            elem=type_elem,
        )

    def _update_flags(self, parent: ET.Element, flags: dict[str, str]) -> None:
        f = parent.find("flags")
        if not flags:
            if f is not None:
                parent.remove(f)
            return
        if f is None:
            f = ET.SubElement(parent, "flags")
        f.attrib.clear()
        f.attrib.update(flags)

    def _update_named_elements(
        self, parent: ET.Element, tag: str, names: str, multi: bool = False
    ) -> None:
        if multi:
            for elem in parent.findall(tag):
                parent.remove(elem)

            for part in names.split(";"):
                part = part.strip()
                if part:
                    ET.SubElement(parent, tag).set("name", part)
        return

        elems = parent.findall(tag)
        existing = elems[0] if elems else None

        if names.strip():
            if existing is not None:
                existing.set("name", names.strip())
            else:
                ET.SubElement(parent, tag).set("name", names.strip())
        elif existing is not None:
            parent.remove(existing)
