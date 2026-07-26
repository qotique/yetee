from __future__ import annotations

from lxml import etree as ET

from models.field_def import STATIC_FIELD_DEFS
from models.row_data import RowData
from repository.file_cache import FileCache


def _elem_text(parent: ET.Element, tag: str, default: str = "") -> str:
    elem = parent.find(tag)
    if elem is not None and elem.text:
        return elem.text.strip()
    return default


def _set_elem_text(parent: ET.Element, tag: str, value: str) -> None:
    elem = parent.find(tag)
    if elem is not None:
        if value:
            elem.text = value
        else:
            parent.remove(elem)
    elif value:
        ET.SubElement(parent, tag).text = value


def _names_to_str(elems: list[ET.Element]) -> str:
    names = [e.get("name", "") for e in elems if e.get("name")]
    return ", ".join(names)


class XmlRepository:
    def __init__(self, cache: FileCache | None = None):
        self._cache = cache or FileCache()

    def parse_file(self, path: str) -> list[RowData]:
        cached = self._cache.get_rows(path)
        if cached is not None:
            return cached

        tree = ET.parse(path)
        self._cache.set_tree(path, tree)
        root = tree.getroot()
        rows = [self._build_row(t) for t in root.findall("type")]
        self._cache.set_rows(path, rows)
        return rows

    def save(self, path: str, rows: list[RowData]) -> None:
        tree = self._cache.get_tree(path)
        if tree is None:
            return

        for row_data in rows:
            elem = row_data.elem
            elem.set("name", row_data.values.get("name", ""))
            _set_elem_text(elem, "nominal", row_data.values.get("nominal", ""))
            _set_elem_text(elem, "lifetime", row_data.values.get("lifetime", ""))
            _set_elem_text(elem, "restock", row_data.values.get("restock", ""))
            _set_elem_text(elem, "min", row_data.values.get("min", ""))
            _set_elem_text(elem, "quantmin", row_data.values.get("quantmin", ""))
            _set_elem_text(elem, "quantmax", row_data.values.get("quantmax", ""))
            _set_elem_text(elem, "cost", row_data.values.get("cost", ""))
            self._update_flags(elem, row_data.flags)
            self._update_single_named(elem, "category", row_data.values.get("category", ""))
            self._update_multi_named(elem, "usage", row_data.values.get("usage", ""))
            self._update_multi_named(elem, "value", row_data.values.get("value", ""))

        ET.indent(tree, space="\t")
        tree.write(path, encoding="UTF-8", xml_declaration=True)

    def invalidate_cache(self, path: str) -> None:
        self._cache.invalidate(path)

    def _build_row(self, type_elem: ET.Element) -> RowData:
        flags_elem = type_elem.find("flags")
        values: dict[str, str] = {}
        for fd in STATIC_FIELD_DEFS:
            if fd.key == "name":
                values[fd.key] = type_elem.get("name", "")
            else:
                values[fd.key] = _elem_text(type_elem, fd.key)

        cat_elem = type_elem.find("category")
        values["category"] = cat_elem.get("name", "") if cat_elem is not None else ""
        values["usage"] = _names_to_str(type_elem.findall("usage"))
        values["value"] = _names_to_str(type_elem.findall("value"))

        return RowData(
            values=values,
            flags={k: v for k, v in flags_elem.attrib.items()} if flags_elem is not None else {},
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

    def _update_single_named(self, parent: ET.Element, tag: str, name: str) -> None:
        elems = parent.findall(tag)
        existing = elems[0] if elems else None
        if name.strip():
            if existing is not None:
                existing.set("name", name.strip())
            else:
                ET.SubElement(parent, tag).set("name", name.strip())
        else:
            if existing is not None:
                parent.remove(existing)

    def _update_multi_named(self, parent: ET.Element, tag: str, s: str) -> None:
        for elem in parent.findall(tag):
            parent.remove(elem)
        for part in s.split(","):
            part = part.strip()
            if part:
                ET.SubElement(parent, tag).set("name", part)
