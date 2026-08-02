from __future__ import annotations

from lxml import etree as ET


def elem_text(parent: ET.Element, tag: str, default: str = "") -> str:
    elem = parent.find(tag)
    if elem is not None and elem.text:
        return str(elem.text).strip()
    return default


def set_elem_text(parent: ET.Element, tag: str, value: str) -> None:
    elem = parent.find(tag)
    if elem is not None:
        if value:
            elem.text = value
        else:
            parent.remove(elem)
    elif value:
        ET.SubElement(parent, tag).text = value
