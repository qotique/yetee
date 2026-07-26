from __future__ import annotations

from dataclasses import dataclass, field

from lxml import etree as ET


@dataclass
class RowData:
    values: dict[str, str] = field(default_factory=dict)
    flags: dict[str, str] = field(default_factory=dict)
    elem: ET.Element | None = None
