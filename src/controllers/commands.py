from __future__ import annotations

import random
from collections.abc import Iterable

from models.field_def import CATEGORIES, USAGES, VALUES_LIST
from models.row_data import RowData
from core.protocols import IXmlRepository

LIFETIME_OPTIONS = [300, 600, 1800, 3600, 7200, 14400, 28800, 43200, 86400, 3888000]
RESTOCK_OPTIONS = [60, 120, 300, 600, 900, 1800, 3600, 7200]


class RandomizeCommand:
    def __init__(self, rows: list[RowData], target_indices: Iterable[int]) -> None:
        self._rows = rows
        self._target_indices = set(target_indices)

    def execute(self) -> None:
        for idx in self._target_indices:
            row = self._rows[idx]
            row.values["nominal"] = str(random.randint(1, 200))
            row.values["lifetime"] = str(random.choice(LIFETIME_OPTIONS))
            row.values["restock"] = str(random.choice(RESTOCK_OPTIONS))
            row.values["min"] = str(random.randint(0, 50))
            row.values["quantmin"] = str(random.randint(-1, 10))
            row.values["quantmax"] = str(random.randint(1, 50))
            row.values["cost"] = str(random.randint(-1, 500))
            row.values["category"] = random.choice(CATEGORIES)
            row.values["usage"] = ", ".join(
                random.sample(USAGES, random.randint(1, 3))
            )
            row.values["value"] = random.choice(VALUES_LIST)
            for flag in row.flags:
                row.flags[flag] = random.choice(["0", "1"])


class SaveCommand:
    def __init__(
        self,
        repo: IXmlRepository,
        path: str,
        rows: list[RowData],
    ) -> None:
        self._repo = repo
        self._path = path
        self._rows = rows

    def execute(self) -> None:
        self._repo.save(self._path, self._rows)

    async def execute_async(self) -> None:
        await self._repo.save_async(self._path, self._rows)