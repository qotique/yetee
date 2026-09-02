from __future__ import annotations

from unittest.mock import MagicMock

import flet as ft
import pytest

from commands.protocols import IAppCommand
from commands.registry import AppCommand, CommandRegistry
from ui.menu_bar import MENU_SPECS, CommandMenuBar, MenuGroupSpec, MenuItemSpec
from ui.economy_editor import EconomyEditor


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


@pytest.fixture
def registry() -> CommandRegistry:
    return CommandRegistry()


def test_app_command_static(registry: CommandRegistry) -> None:
    handler = MagicMock()
    command = AppCommand("save", "Save", handler)
    registry.register(command)
    assert registry.get("save") is command
    assert command.command_id == "save"
    assert command.title == "Save"
    assert command.enabled is True
    registry.execute("save")
    handler.assert_called_once_with()


def test_app_command_dynamic_title_and_enabled() -> None:
    command = AppCommand(
        "add_row",
        "Add",
        MagicMock(),
        enabled_fn=lambda: False,
        title_fn=lambda: "Disable multi-select",
    )
    assert command.enabled is False
    assert command.title == "Disable multi-select"


def test_registry_execute_disabled_noop() -> None:
    handler = MagicMock()
    command = AppCommand("delete", "Delete", handler, enabled_fn=lambda: False)
    registry = CommandRegistry()
    registry.register(command)
    registry.execute("delete")
    handler.assert_not_called()


def test_registry_invoke_bypasses_enabled() -> None:
    handler = MagicMock()
    command = AppCommand("delete", "Delete", handler, enabled_fn=lambda: False)
    registry = CommandRegistry()
    registry.register(command)
    registry.invoke("delete")
    handler.assert_called_once_with()


def test_registry_invoke_missing_noop() -> None:
    handler = MagicMock()
    command = AppCommand("missing", "Missing", handler)
    registry = CommandRegistry()
    registry.register(command)
    registry.invoke("other")
    handler.assert_not_called()


def test_registry_execute_missing_noop() -> None:
    handler = MagicMock()
    command = AppCommand("missing", "Missing", handler)
    registry = CommandRegistry()
    registry.register(command)
    registry.execute("other")
    handler.assert_not_called()


def test_registry_observer() -> None:
    registry = CommandRegistry()
    listener = MagicMock()
    registry.subscribe(listener)
    commanded = AppCommand("x", "X", MagicMock())
    registry.register(commanded)
    registry.execute("x")
    assert listener.call_count == 1
    registry.refresh()
    assert listener.call_count == 2


def test_registry_all() -> None:
    registry = CommandRegistry()
    registry.register(AppCommand("a", "A", MagicMock()))
    registry.register(AppCommand("b", "B", MagicMock()))
    assert [c.command_id for c in registry.all()] == ["a", "b"]


def test_app_command_matches_protocol() -> None:
    command: IAppCommand = AppCommand("id", "Title", MagicMock())
    assert command.command_id == "id"


def test_menu_bar_builds_specs() -> None:
    registry = CommandRegistry()
    registry.register(AppCommand("save", "Save", MagicMock()))
    bar = CommandMenuBar(registry, MENU_SPECS)
    assert isinstance(bar.control, ft.MenuBar)
    assert bar.control.controls
    assert "save" in bar._items


def test_menu_item_click_executes_command() -> None:
    handler = MagicMock()
    registry = CommandRegistry()
    registry.register(AppCommand("save", "Save", handler))
    groups = [
        MenuGroupSpec(
            "File",
            [
                MenuItemSpec("save", "Save"),
            ],
        )
    ]
    bar = CommandMenuBar(registry, groups)
    widget = bar._items["save"]
    widget.on_click(object())
    handler.assert_called_once_with()


def test_menu_refresh_updates_disabled() -> None:
    enabled = False
    registry = CommandRegistry()
    registry.register(
        AppCommand("save", "Save", MagicMock(), enabled_fn=lambda: enabled)
    )
    bar = CommandMenuBar(registry, [MenuGroupSpec("File", [MenuItemSpec("save", "Save")])])
    widget = bar._items["save"]
    assert widget.disabled is True
    enabled = True
    bar.refresh()
    assert widget.disabled is False


def test_menu_refresh_updates_title() -> None:
    title = "Enable multi-select"
    registry = CommandRegistry()
    registry.register(
        AppCommand(
            "toggle_multi_select",
            "Multi-select",
            MagicMock(),
            title_fn=lambda: title,
        )
    )
    bar = CommandMenuBar(
        registry, [MenuGroupSpec("Edit", [MenuItemSpec("toggle_multi_select")])]
    )
    widget = bar._items["toggle_multi_select"]
    assert widget.content.value == "Enable multi-select"
    title = "Disable multi-select"
    bar.refresh()
    assert widget.content.value == "Disable multi-select"


@pytest.fixture
def editor(mock_page) -> EconomyEditor:
    return EconomyEditor(
        page=mock_page,
        file_display=MagicMock(),
        event_display=MagicMock(),
        profile_service=MagicMock(),
        unavailable_display=MagicMock(),
    )


def test_editor_dispatch_none_entity(editor: EconomyEditor) -> None:
    editor._current_entity = None
    editor.undo_current()
    editor.file_display.undo.assert_not_called()


def test_editor_dispatch_undo(editor: EconomyEditor) -> None:
    from ui.economy_editor import TYPES_ENTITY

    editor._current_entity = TYPES_ENTITY
    editor.undo_current()
    editor.file_display.undo.assert_called_once_with(None)
    editor.file_display.undo.reset_mock()
    editor.undo_current("event")
    editor.file_display.undo.assert_called_once_with("event")


def test_editor_dispatch_capabilities(editor: EconomyEditor) -> None:
    from ui.economy_editor import TYPES_ENTITY

    editor._current_entity = None
    assert editor.can_undo is False
    editor._current_entity = TYPES_ENTITY
    editor.file_display.can_undo = True
    assert editor.can_undo is True


def test_editor_add_label(editor: EconomyEditor) -> None:
    from ui.economy_editor import TYPES_ENTITY

    editor._current_entity = None
    assert editor.add_label() == "Add"
    editor._current_entity = TYPES_ENTITY
    assert editor.add_label() == "Add Type"
    editor._current_entity = "Events"
    assert editor.add_label() == "Add Event"


def test_editor_multi_select_label(editor: EconomyEditor) -> None:
    from ui.economy_editor import TYPES_ENTITY

    editor._current_entity = TYPES_ENTITY
    editor.file_display.multi_select_mode = False
    assert editor.multi_select_label() == "Enable multi-select"
    editor.file_display.multi_select_mode = True
    assert editor.multi_select_label() == "Disable multi-select"