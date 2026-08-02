from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

SRC_DIR = str(Path(__file__).resolve().parent.parent / "src")
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)


@pytest.fixture(autouse=True)
def patch_async(monkeypatch):
    """Replace asyncio.create_task with a no-op mock so sync tests work."""
    mock_task = MagicMock()
    mock_task.done.return_value = False

    def _noop_create_task(coro, **kw):
        coro.close()
        return mock_task

    monkeypatch.setattr(asyncio, "create_task", _noop_create_task)
    return mock_task


@pytest.fixture(autouse=True)
def patch_flet_update(monkeypatch):
    """Flet controls raise if not attached to a page; make update a no-op in tests."""
    import flet as ft

    monkeypatch.setattr(ft.Control, "update", lambda self: None)


SMALL_TYPES_XML = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<types>
  <type name="Item_Weapon_Knife">
    <nominal>10</nominal>
    <lifetime>14400</lifetime>
    <restock>1800</restock>
    <min>6</min>
    <quantmin>-1</quantmin>
    <quantmax>-1</quantmax>
    <cost>100</cost>
    <flags count_in_cargo="0" count_in_hoarder="0" count_in_map="1" count_in_player="0" crafted="0" deloot="0"/>
    <category name="weapons"/>
    <usage name="Military"/>
    <usage name="Police"/>
    <value name="Tier3"/>
  </type>
  <type name="Item_Weapon_Gun">
    <nominal>5</nominal>
    <lifetime>28800</lifetime>
    <restock>3600</restock>
    <min>2</min>
    <quantmin>-1</quantmin>
    <quantmax>-1</quantmax>
    <cost>200</cost>
    <flags count_in_cargo="1" count_in_hoarder="0" count_in_map="1" count_in_player="0" crafted="0" deloot="0"/>
    <category name="weapons"/>
    <usage name="Military"/>
    <value name="Tier2"/>
  </type>
  <type name="Food_Can">
    <nominal>50</nominal>
    <lifetime>7200</lifetime>
    <restock>900</restock>
    <min>20</min>
    <quantmin>1</quantmin>
    <quantmax>3</quantmax>
    <cost>0</cost>
    <flags count_in_cargo="1" count_in_hoarder="0" count_in_map="1" count_in_player="1" crafted="0" deloot="0"/>
    <category name="food"/>
    <usage name="Town"/>
    <usage name="Village"/>
    <value name="Tier1"/>
  </type>
</types>
"""

LARGE_TYPES_XML_ROW = """  <type name="Item_Test_{n}">
    <nominal>{n}</nominal>
    <lifetime>14400</lifetime>
    <restock>1800</restock>
    <min>6</min>
    <quantmin>-1</quantmin>
    <quantmax>-1</quantmax>
    <cost>100</cost>
    <flags count_in_cargo="0" count_in_hoarder="0" count_in_map="1" count_in_player="0" crafted="0" deloot="0"/>
    <category name="weapons"/>
    <usage name="Military"/>
    <value name="Tier3"/>
  </type>
"""


def _make_large_xml(row_count: int) -> str:
    rows = "\n".join(LARGE_TYPES_XML_ROW.format(n=i) for i in range(row_count))
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<types>\n'
        + rows
        + "\n</types>"
    )


@pytest.fixture
def small_types_file(tmp_path):
    path = tmp_path / "types.xml"
    path.write_text(SMALL_TYPES_XML)
    return path


@pytest.fixture
def large_types_file(tmp_path):
    path = tmp_path / "types_large.xml"
    path.write_text(_make_large_xml(55))
    return path


@pytest.fixture
def mock_page():
    page = MagicMock()
    page.theme = None
    page.dark_theme = None
    page.on_keyboard_event = None
    mock_task = MagicMock()
    mock_task.done.return_value = False
    page.run_task.return_value = mock_task
    return page
