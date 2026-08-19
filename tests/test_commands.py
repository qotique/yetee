"""Tests for command objects (RandomizeCommand, SaveCommand)."""

from __future__ import annotations

from unittest.mock import AsyncMock, Mock

from controllers.commands import LIFETIME_OPTIONS, RESTOCK_OPTIONS, RandomizeCommand, SaveCommand
from models.row_data import RowData
from protocols import IXmlRepository


def _row() -> RowData:
    return RowData(
        values={
            "name": "Test_Item",
            "nominal": "10",
            "lifetime": "3600",
            "restock": "300",
            "min": "5",
            "quantmin": "-1",
            "quantmax": "10",
            "cost": "-1",
            "category": "food",
            "usage": "Town",
            "value": "Tier1",
        },
        flags={"cargo": "0", "map": "1"},
    )


def test_randomize_command_only_touches_target_rows():
    rows = [_row(), _row()]
    RandomizeCommand(rows, {0}).execute()
    assert rows[0].values["nominal"] != "10"
    assert rows[1].values["nominal"] == "10"


def test_randomize_command_produces_valid_choices():
    rows = [_row()]
    RandomizeCommand(rows, {0}).execute()
    row = rows[0]
    assert row.values["lifetime"] in [str(v) for v in LIFETIME_OPTIONS]
    assert row.values["restock"] in [str(v) for v in RESTOCK_OPTIONS]
    assert row.values["category"] != ""
    assert row.values["usage"] != ""
    assert row.values["value"] != ""
    assert all(v in ("0", "1") for v in row.flags.values())


def test_save_command_calls_repository():
    repo = Mock(spec=IXmlRepository)
    rows = [_row()]
    SaveCommand(repo, "/tmp/types.xml", rows).execute()
    repo.save.assert_called_once_with("/tmp/types.xml", rows)


async def test_save_command_async():
    repo = Mock(spec=IXmlRepository)
    repo.save_async = AsyncMock()
    rows = [_row()]
    await SaveCommand(repo, "/tmp/types.xml", rows).execute_async()
    repo.save_async.assert_awaited_once_with("/tmp/types.xml", rows)