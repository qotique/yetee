from __future__ import annotations

import logging
from dataclasses import dataclass, field

import flet as ft

from commands.registry import CommandRegistry

logger = logging.getLogger(__name__)

_MENU_BUTTON_STYLE = ft.ButtonStyle(
    padding=ft.Padding(left=12, top=6, right=12, bottom=6),
)

_TOP_LEVEL_STYLE = ft.ButtonStyle(
    padding=ft.Padding.all(0),
    overlay_color=ft.Colors.TRANSPARENT,
)


@dataclass
class MenuItemSpec:
    command_id: str
    title: str | None = None
    shortcut: str | None = None
    children: list[MenuItemSpec] = field(default_factory=list)
    divider_after: bool = False


@dataclass
class MenuGroupSpec:
    title: str
    items: list[MenuItemSpec]


MENU_SPECS: list[MenuGroupSpec] = [
    MenuGroupSpec(
        title="File",
        items=[
            MenuItemSpec("new_project", "New Project"),
            MenuItemSpec("open_project", "Open Project"),
            MenuItemSpec("delete_project", "Delete Project"),
            MenuItemSpec("save", "Save", shortcut="Ctrl+S", divider_after=True),
            MenuItemSpec("reload", "Reload"),
            MenuItemSpec("settings", "Settings", divider_after=True),
            MenuItemSpec("connections", "Connections"),
            MenuItemSpec("close", "Close Window"),
        ],
    ),
    MenuGroupSpec(
        title="Edit",
        items=[
            MenuItemSpec("undo", "Undo", shortcut="Ctrl+Z"),
            MenuItemSpec("redo", "Redo", shortcut="Ctrl+Y", divider_after=True),
            MenuItemSpec("add_row", "Add"),
            MenuItemSpec("delete_row", "Delete"),
            MenuItemSpec("toggle_multi_select", "Multi-select"),
        ],
    ),
    MenuGroupSpec(
        title="View",
        items=[
            MenuItemSpec("prev_page", "Previous Page"),
            MenuItemSpec("next_page", "Next Page"),
        ],
    ),
]


class CommandMenuBar:
    def __init__(
        self,
        registry: CommandRegistry,
        groups: list[MenuGroupSpec] | None = None,
    ) -> None:
        self._registry = registry
        self._items: dict[str, ft.MenuItemButton] = {}
        top_level = [self._build_group(spec) for spec in groups or MENU_SPECS]
        self.control = ft.MenuBar(controls=top_level)
        registry.subscribe(self.refresh)
        self.refresh()

    def refresh(self) -> None:
        changed: list[ft.Control] = []
        for command_id, widget in self._items.items():
            command = self._registry.get(command_id)
            if command is None:
                continue
            title = getattr(widget.content, "value", None)
            if title != command.title:
                widget.content = ft.Text(command.title)
                changed.append(widget)
            disabled = not command.enabled
            if widget.disabled != disabled:
                widget.disabled = disabled
                changed.append(widget)
        for widget in changed:
            self._safe_update(widget)

    def _build_group(self, spec: MenuGroupSpec) -> ft.SubmenuButton:
        controls: list[ft.Control] = []
        for item in spec.items:
            controls.append(self._build_item(item))
            if item.divider_after:
                controls.append(ft.Divider(height=1))
        text = ft.Text(spec.title)

        def _set_active(active: bool) -> None:
            desired = (
                ft.TextStyle(decoration=ft.TextDecoration.UNDERLINE)
                if active
                else None
            )
            if text.style == desired:
                return
            text.style = desired
            text.update()

        def _on_hover(e: ft.ControlEvent) -> None:
            data = e.data
            active = (
                data
                if isinstance(data, bool)
                else str(data).strip().lower() == "true"
            )
            _set_active(active)

        label = ft.Container(
            content=text,
            padding=ft.Padding(left=12, top=0, right=12, bottom=0),
            on_hover=_on_hover,
        )

        return ft.SubmenuButton(
            content=label,
            controls=controls,
            style=_TOP_LEVEL_STYLE,
            on_hover=_on_hover,
            on_open=lambda e: _set_active(True),
            on_close=lambda e: _set_active(False),
        )

    def _build_item(self, spec: MenuItemSpec) -> ft.Control:
        if spec.children:
            controls = [self._build_item(child) for child in spec.children]
            return ft.SubmenuButton(
                content=ft.Text(spec.title or spec.command_id),
                controls=controls,
                style=_MENU_BUTTON_STYLE,
            )
        widget = ft.MenuItemButton(
            content=ft.Text(spec.title or spec.command_id),
            trailing=ft.Text(spec.shortcut) if spec.shortcut else None,
            style=_MENU_BUTTON_STYLE,
            on_click=lambda _e, cid=spec.command_id: self._registry.execute(cid),
        )
        self._items[spec.command_id] = widget
        return widget

    def _safe_update(self, control: ft.Control) -> None:
        try:
            control.update()
        except RuntimeError:
            pass