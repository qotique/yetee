from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto

import flet as ft


class FieldType(Enum):
    TEXT = auto()
    FLAG = auto()
    SINGLE_NAMED = auto()
    MULTI_NAMED = auto()


@dataclass
class FieldDef:
    key: str
    label: str
    type: FieldType
    width: int = 100
    align: ft.TextAlign = ft.TextAlign.LEFT
    options: list[str] | None = None

    def is_flag(self) -> bool:
        return self.type == FieldType.FLAG

    def is_text(self) -> bool:
        return self.type == FieldType.TEXT

    def is_single_named(self) -> bool:
        return self.type == FieldType.SINGLE_NAMED

    def is_multi_named(self) -> bool:
        return self.type == FieldType.MULTI_NAMED


STATIC_FIELD_DEFS: list[FieldDef] = [
    FieldDef(
        "name",
        "Name",
        FieldType.TEXT,
        width=200,
    ),
    FieldDef(
        "nominal",
        "Nominal",
        FieldType.TEXT,
        width=88,
        align=ft.TextAlign.RIGHT,
    ),
    FieldDef(
        "lifetime",
        "Lifetime",
        FieldType.TEXT,
        width=96,
        align=ft.TextAlign.RIGHT,
    ),
    FieldDef(
        "restock",
        "Restock",
        FieldType.TEXT,
        width=88,
        align=ft.TextAlign.RIGHT,
    ),
    FieldDef(
        "min",
        "Min",
        FieldType.TEXT,
        width=48,
        align=ft.TextAlign.RIGHT,
    ),
    FieldDef(
        "quantmin",
        "QuantMin",
        FieldType.TEXT,
        width=96,
        align=ft.TextAlign.RIGHT,
    ),
    FieldDef(
        "quantmax",
        "QuantMax",
        FieldType.TEXT,
        width=96,
        align=ft.TextAlign.RIGHT,
    ),
    FieldDef(
        "cost",
        "Cost",
        FieldType.TEXT,
        width=56,
        align=ft.TextAlign.RIGHT,
    ),
]

NUM_BASE_COLS = len(STATIC_FIELD_DEFS)

CATEGORIES = [
    "clothes",
    "containers",
    "explosives",
    "food",
    "lootdispatch",
    "tools",
    "weapons",
]
USAGES = [
    "Coast",
    "ContaminatedArea",
    "Farm",
    "Firefighter",
    "Historical",
    "Hunting",
    "Industrial",
    "Lunapark",
    "Medic",
    "Military",
    "Office",
    "Police",
    "Prison",
    "School",
    "SeasonalEvent",
    "Town",
    "Village",
]
VALUES_LIST = ["Tier0", "Tier1", "Tier2", "Tier3", "Tier4", "Unique"]
