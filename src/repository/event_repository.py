from __future__ import annotations

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from lxml import etree as ET

from core.exceptions import ParseError, AccessError
from models.row_data import RowData
from repository.file_cache import FileCache
from repository.xml_utils import elem_text, set_elem_text

logger = logging.getLogger(__name__)

_executor = ThreadPoolExecutor(max_workers=2)


EVENT_FLAG_NAMES = ["deletable", "init_random", "remove_damaged"]

EVENT_POSITION_OPTIONS = ["fixed", "player", "uniform"]
EVENT_LIMIT_OPTIONS = ["mixed", "child", "custom", "parent"]


class EventRepository:
    def __init__(self, cache: FileCache | None = None):
        self._cache = cache or FileCache()

    def parse_file(self, path: str) -> list[RowData]:
        cached = self._cache.get_rows(path)
        if cached is not None:
            logger.debug("Cache hit for %s", path)
            return cached

        logger.info("Parsing events file: %s", path)
        try:
            tree = ET.parse(path)
        except ET.ParseError as ex:
            raise ParseError(f"Failed to parse {path}: {ex}") from ex
        except FileNotFoundError as ex:
            raise AccessError(f"File not found: {path}") from ex
        except Exception as ex:
            raise AccessError(f"Cannot read {path}: {ex}") from ex

        self._cache.set_tree(path, tree)
        root = tree.getroot()
        rows = [self._build_row(t) for t in root.findall("event")]
        self._cache.set_rows(path, rows)
        logger.debug("Parsed %d events from %s", len(rows), path)
        return rows

    async def parse_file_async(self, path: str) -> list[RowData]:
        cached = self._cache.get_rows(path)
        if cached is not None:
            return cached
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(_executor, self._parse_file_sync, path)

    def _parse_file_sync(self, path: str) -> list[RowData]:
        return self.parse_file(path)

    def parse_spawns(self, path: str) -> dict[str, list[dict[str, str]]]:
        spawns: dict[str, list[dict[str, str]]] = {}
        if not Path(path).exists():
            logger.debug("Spawns file not found: %s", path)
            return spawns
        try:
            tree = ET.parse(path)
        except ET.ParseError as ex:
            logger.warning("Failed to parse spawns %s: %s", path, ex)
            return spawns
        root = tree.getroot()
        for event_elem in root.findall("event"):
            name = event_elem.get("name", "")
            if not name:
                continue
            pos_list: list[dict[str, str]] = []
            zone_attrs: dict[str, str] = {}
            zone_elem = event_elem.find("zone")
            if zone_elem is not None:
                zone_attrs = dict(zone_elem.attrib)
            for pos_elem in event_elem.findall("pos"):
                attrs = dict(pos_elem.attrib)
                pos_list.append(attrs)
            spawns[name] = {
                "positions": pos_list,
                "zone": zone_attrs,
            }
        return spawns

    def save(self, path: str, rows: list[RowData]) -> None:
        logger.info("Saving %d events to %s", len(rows), path)
        tree = self._cache.get_tree(path)
        if tree is None:
            try:
                tree = ET.parse(path)
                self._cache.set_tree(path, tree)
            except Exception as ex:
                raise ParseError(f"Cannot re-parse {path}: {ex}") from ex
        if tree is None:
            raise ParseError(f"No element tree available for {path}")

        root = tree.getroot()
        existing = {e.get("name", ""): e for e in root.findall("event")}
        seen: set[str] = set()

        for row_data in rows:
            elem = row_data.elem
            name = row_data.values.get("name", "")
            if elem is None:
                elem = ET.SubElement(root, "event")
                elem.set("name", name)
                row_data.elem = elem
                existing[name] = elem
            else:
                if elem.get("name", "") != name:
                    elem.set("name", name)
            seen.add(name)

            set_elem_text(elem, "nominal", row_data.values.get("nominal", ""))
            set_elem_text(elem, "min", row_data.values.get("min", ""))
            set_elem_text(elem, "max", row_data.values.get("max", ""))
            set_elem_text(elem, "lifetime", row_data.values.get("lifetime", ""))
            set_elem_text(elem, "restock", row_data.values.get("restock", ""))
            set_elem_text(elem, "saferadius", row_data.values.get("saferadius", ""))
            set_elem_text(
                elem, "distanceradius", row_data.values.get("distanceradius", "")
            )
            set_elem_text(
                elem, "cleanupradius", row_data.values.get("cleanupradius", "")
            )
            set_elem_text(elem, "position", row_data.values.get("position", ""))
            set_elem_text(elem, "limit", row_data.values.get("limit", ""))
            set_elem_text(elem, "active", row_data.values.get("active", ""))
            secondary = row_data.values.get("secondary", "")
            if secondary:
                set_elem_text(elem, "secondary", secondary)
            else:
                sec_elem = elem.find("secondary")
                if sec_elem is not None:
                    elem.remove(sec_elem)

            self._update_flags(elem, row_data.flags)

        for ename, eelem in existing.items():
            if ename not in seen:
                root.remove(eelem)

        try:
            ET.indent(tree, space="\t")
            tree.write(path, encoding="UTF-8", xml_declaration=True)
            logger.info("Saved events to %s successfully", path)
        except Exception as ex:
            raise AccessError(f"Failed to save {path}: {ex}") from ex

    async def save_async(self, path: str, rows: list[RowData]) -> None:
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(_executor, self._save_sync, path, rows)

    def _save_sync(self, path: str, rows: list[RowData]) -> None:
        self.save(path, rows)

    def invalidate_cache(self, path: str) -> None:
        self._cache.invalidate(path)
        logger.debug("Invalidated cache for %s", path)

    def _build_row(self, event_elem: ET.Element) -> RowData:
        values: dict[str, str] = {
            "name": event_elem.get("name", ""),
            "nominal": elem_text(event_elem, "nominal"),
            "min": elem_text(event_elem, "min"),
            "max": elem_text(event_elem, "max"),
            "lifetime": elem_text(event_elem, "lifetime"),
            "restock": elem_text(event_elem, "restock"),
            "saferadius": elem_text(event_elem, "saferadius"),
            "distanceradius": elem_text(event_elem, "distanceradius"),
            "cleanupradius": elem_text(event_elem, "cleanupradius"),
            "position": elem_text(event_elem, "position"),
            "limit": elem_text(event_elem, "limit"),
            "active": elem_text(event_elem, "active"),
            "secondary": elem_text(event_elem, "secondary"),
        }

        flags_elem = event_elem.find("flags")
        flags: dict[str, str] = {}
        if flags_elem is not None:
            for fn in EVENT_FLAG_NAMES:
                v = flags_elem.get(fn)
                if v is not None:
                    flags[fn] = v

        values["child_count"] = "0"
        values["spawn_count"] = "0"

        return RowData(values=values, flags=flags, elem=event_elem)

    def _update_flags(self, parent: ET.Element, flags: dict[str, str]) -> None:
        f = parent.find("flags")
        if not flags:
            if f is not None:
                parent.remove(f)
            return
        if f is None:
            f = ET.SubElement(parent, "flags")
        f.attrib.clear()
        for k in EVENT_FLAG_NAMES:
            if k in flags:
                f.attrib[k] = flags[k]
            else:
                f.attrib[k] = "0"

    def get_children(self, row: RowData) -> list[dict[str, str]]:
        if row.elem is None:
            return []
        children: list[dict[str, str]] = []
        for child in row.elem.findall("children/child"):
            children.append(dict(child.attrib))
        return children

    def set_children(self, row: RowData, children: list[dict[str, str]]) -> None:
        if row.elem is None:
            return
        children_elem = row.elem.find("children")
        if children_elem is None:
            children_elem = ET.SubElement(row.elem, "children")
        for child in children_elem.findall("child"):
            children_elem.remove(child)
        for attrs in children:
            if not attrs.get("type"):
                continue
            child_elem = ET.SubElement(children_elem, "child")
            for k in ("type", "min", "max", "lootmin", "lootmax"):
                v = attrs.get(k, "")
                if v:
                    child_elem.set(k, v)

    def save_spawns(self, path: str, spawns: dict[str, dict]) -> None:
        logger.info("Saving spawns to %s", path)
        root = ET.Element("eventposdef")
        root.set("standalone", "yes")
        for ename in sorted(spawns.keys()):
            info = spawns[ename]
            if isinstance(info, dict):
                positions = info.get("positions", [])
                zone = info.get("zone", {})
            else:
                positions = info if isinstance(info, list) else []
                zone = {}
            if not positions and not zone:
                ET.SubElement(root, "event", name=ename)
                continue
            event_elem = ET.SubElement(root, "event", name=ename)
            if zone:
                zone_elem = ET.SubElement(event_elem, "zone")
                for k in ("smin", "smax", "dmin", "dmax", "r"):
                    v = zone.get(k)
                    if v:
                        zone_elem.set(k, v)
            for pos in positions:
                pos_elem = ET.SubElement(event_elem, "pos")
                for k in ("x", "z", "y", "a"):
                    v = pos.get(k)
                    if v:
                        pos_elem.set(k, v)
                for k in sorted(pos.keys()):
                    if k not in ("x", "z", "y", "a") and (v := pos.get(k)):
                        pos_elem.set(k, v)
        try:
            tree = ET.ElementTree(root)
            ET.indent(tree, space="\t")
            tree.write(path, encoding="UTF-8", xml_declaration=True)
            logger.info("Saved spawns to %s successfully", path)
        except Exception as ex:
            raise AccessError(f"Failed to save spawns {path}: {ex}") from ex
