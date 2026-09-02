from __future__ import annotations

import logging

import flet as ft

from controllers.settings_manager import SettingsManager
from commands.registry import CommandRegistry
from services.entertainment_service import EntertainmentService
from services.settings_service import LANGUAGES, THEMES

logger = logging.getLogger(__name__)


class AppShell:
    def __init__(
        self,
        page: ft.Page,
        entertainment_service: EntertainmentService,
        command_registry: CommandRegistry | None = None,
    ) -> None:
        self.page = page
        self._entertainment = entertainment_service
        self._commands = command_registry
        self._editor_control: ft.Control | None = None
        self._build_controls()

    def _build_controls(self) -> None:
        self.project_dropdown = ft.Dropdown(
            label="Project",
            options=[],
            text_size=12,
            width=200,
            dense=True,
            content_padding=ft.Padding(4, 0, 4, 0),
        )
        self.delete_project_btn = ft.IconButton(
            icon=ft.Icons.DELETE,
            tooltip="Delete current project",
            visible=False,
        )
        self.new_project_btn = ft.IconButton(
            icon=ft.Icons.ADD_BOX,
            tooltip="New Project",
        )
        self.entity_dropdown = ft.Dropdown(
            label="Entity",
            text_size=12,
            options=[],
            width=170,
            dense=True,
            content_padding=ft.Padding(4, 0, 4, 0),
            visible=False,
        )
        self.save_btn = ft.Button(
            "Save",
            icon=ft.Icons.SAVE,
            visible=False,
        )
        self.refresh_btn = ft.IconButton(
            icon=ft.Icons.REFRESH,
            tooltip="Refresh project",
            visible=False,
        )

        self.start_new_project_btn = ft.Button(
            "New Project",
            icon=ft.Icons.ADD_BOX,
        )
        self.start_ssh_btn = ft.Button(
            "Connect via SSH",
            icon=ft.Icons.LAN,
        )
        self.start_ftp_btn = ft.Button(
            "Connect via FTP",
            icon=ft.Icons.CLOUD,
        )
        self.start_open_project_btn = ft.Button(
            "Open Project",
            icon=ft.Icons.FILE_OPEN,
        )
        self.start_select_dir_btn = ft.Button(
            "Select economy directory",
            icon=ft.Icons.FOLDER_OPEN,
        )

        self.start_container = ft.Container(
            width=500,
            expand=True,
            content=ft.Column(
                [
                    ft.Text(
                        "Yet Another Types Editing Environment",
                        size=20,
                        weight=ft.FontWeight.BOLD,
                        text_align=ft.TextAlign.CENTER,
                    ),
                    ft.Text(
                        "Create or open a project to edit DayZ economy files",
                        size=14,
                        text_align=ft.TextAlign.CENTER,
                        color=ft.Colors.GREY_500,
                    ),
                    ft.Divider(height=20, color=ft.Colors.TRANSPARENT),
                    self.start_new_project_btn,
                    self.start_ssh_btn,
                    self.start_ftp_btn,
                    self.start_open_project_btn,
                    ft.Divider(height=10, color=ft.Colors.TRANSPARENT),
                    ft.Text(
                        "Quick start:",
                        size=12,
                        italic=True,
                        color=ft.Colors.GREY_500,
                    ),
                    self.start_select_dir_btn,
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                alignment=ft.MainAxisAlignment.CENTER,
                expand=True,
            ),
        )

        self.content_column = ft.Column(
            controls=[
                self.start_container,
            ],
            alignment=ft.MainAxisAlignment.START,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            expand=True,
        )

        self.settings_btn = ft.IconButton(icon=ft.Icons.SETTINGS)
        self.connections_btn = ft.IconButton(
            icon=ft.Icons.SWAP_VERT_CIRCLE,
            tooltip="Connections",
        )

        self.theme_dropdown = ft.Dropdown(
            label="Theme",
            value="SYSTEM",
            options=[ft.DropdownOption(key=t) for t in THEMES],
            width=200,
        )
        self.language_dropdown = ft.Dropdown(
            label="Language",
            value="English",
            options=[ft.DropdownOption(key=l) for l in LANGUAGES],
            width=200,
        )
        es = self._entertainment
        self.check_updates_switch = ft.Switch(value=True)
        self.fun_messages_switch = ft.Switch(value=es.fun_save_messages)
        self.meme_switch = ft.Switch(value=es.show_meme_on_save)
        self.cat_mode_switch = ft.Switch(value=es.cat_mode)
        self.terminal_mode_switch = ft.Switch(value=es.terminal_mode)
        self.funny_enabled_switch = ft.Switch(value=es.funny_enabled)
        self.unhandled_editors_switch = ft.Switch(value=False)

        self.settings_overlay = ft.Container(
            visible=False,
            expand=True,
            bgcolor=ft.Colors.SURFACE,
            content=ft.Column(
                controls=[
                    ft.Container(
                        content=ft.Row(
                            controls=[
                                ft.IconButton(
                                    icon=ft.Icons.ARROW_BACK,
                                    on_click=self.close_settings,
                                ),
                                ft.Text("Settings", size=20, weight=ft.FontWeight.BOLD),
                            ],
                            alignment=ft.MainAxisAlignment.START,
                        ),
                        bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
                        padding=ft.Padding(left=4, top=8, right=0, bottom=8),
                    ),
                    ft.Divider(height=1),
                    ft.Container(
                        width=500,
                        padding=ft.Padding(left=16, top=16, right=16, bottom=16),
                        content=ft.Column(
                            controls=[
                                ft.ListTile(
                                    title=ft.Text("Theme"),
                                    trailing=self.theme_dropdown,
                                    dense=True,
                                ),
                                ft.ListTile(
                                    title=ft.Text("Language"),
                                    trailing=self.language_dropdown,
                                    dense=True,
                                ),
                                ft.ListTile(
                                    title=ft.Text("Check updates on startup"),
                                    trailing=self.check_updates_switch,
                                    dense=True,
                                ),
                                ft.ListTile(
                                    title=ft.Text("Edit all mods [BETA]"),
                                    trailing=self.unhandled_editors_switch,
                                    dense=True,
                                ),
                                ft.Divider(),
                                ft.Text(
                                    "Entertainment",
                                    weight=ft.FontWeight.BOLD,
                                    size=14,
                                ),
                                ft.ListTile(
                                    title=ft.Text("Fun save messages"),
                                    trailing=self.fun_messages_switch,
                                    dense=True,
                                ),
                                ft.ListTile(
                                    title=ft.Text("Show meme on save"),
                                    trailing=self.meme_switch,
                                    dense=True,
                                ),
                                ft.ListTile(
                                    title=ft.Text("Cat mode"),
                                    trailing=self.cat_mode_switch,
                                    dense=True,
                                ),
                                ft.ListTile(
                                    title=ft.Text("Terminal mode"),
                                    trailing=self.terminal_mode_switch,
                                    dense=True,
                                ),
                                ft.Divider(),
                                ft.Text(
                                    "Fun Buttons",
                                    weight=ft.FontWeight.BOLD,
                                    size=14,
                                ),
                                ft.ListTile(
                                    title=ft.Text("Funny setting (show fun buttons)"),
                                    trailing=self.funny_enabled_switch,
                                    dense=True,
                                ),
                            ],
                            scroll=ft.ScrollMode.AUTO,
                        ),
                    ),
                ],
                expand=True,
            ),
        )

        self._title_row = ft.Row(
            [
                ft.Container(expand=True),
                self.entity_dropdown,
                self.project_dropdown,
                self.new_project_btn,
                self.delete_project_btn,
                self.refresh_btn,
                self.settings_btn,
                self.connections_btn,
                ft.IconButton(
                    icon=ft.Icons.CLOSE,
                    on_click=self._close_window,
                ),
            ],
            spacing=2,
            vertical_alignment=ft.CrossAxisAlignment.CENTER,
        )
        self.title_bar = ft.Container(
            content=ft.WindowDragArea(
                content=self._title_row,
                maximizable=True,
            ),
            bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
            height=56,
            padding=ft.Padding(left=8, top=0, right=4, bottom=0),
        )

        self.content_stack = ft.Stack(
            controls=[
                self.content_column,
                self.settings_overlay,
            ],
            expand=True,
        )

    def attach_editor(self, editor_control: ft.Control) -> None:
        self._editor_control = editor_control
        self.content_column.controls.append(editor_control)

    def attach_menu_bar(self, control: ft.Control) -> None:
        self._title_row.controls.insert(0, control)

    def build_main_view(self) -> ft.View:
        return ft.View(
            route="/",
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[self.title_bar, self.content_stack],
        )

    def ensure_main_view(self) -> None:
        views = self.page.views
        if not views or not views[0].controls:
            views.clear()
            views.append(self.build_main_view())

    def set_project_ui_open(self, opened: bool) -> None:
        if self._editor_control is not None:
            self._editor_control.visible = opened
        self.start_container.visible = not opened
        self.save_btn.visible = opened
        self.delete_project_btn.visible = opened
        self.refresh_btn.visible = opened
        if self._commands is not None:
            self._commands.refresh()

    def refresh_project_options(self, names: list[str], selected: str | None) -> None:
        self.project_dropdown.options = [ft.DropdownOption(key=n) for n in names]
        self.project_dropdown.value = selected
        try:
            self.project_dropdown.update()
        except RuntimeError:
            pass

    def refresh_entity_options(self, entities: list[str], current: str | None) -> None:
        if entities:
            self.entity_dropdown.options = [ft.DropdownOption(key=e) for e in entities]
            self.entity_dropdown.value = current
            self.entity_dropdown.visible = len(entities) > 1
        else:
            self.entity_dropdown.options = []
            self.entity_dropdown.visible = False
        try:
            self.entity_dropdown.update()
        except RuntimeError:
            pass

    def sync_settings_controls(self, manager: SettingsManager) -> None:
        es = self._entertainment
        self.theme_dropdown.value = manager.selected_theme
        self.language_dropdown.value = manager.selected_language
        self.check_updates_switch.value = manager.check_updates
        self.unhandled_editors_switch.value = manager.show_unhandled_mod_editors
        self.fun_messages_switch.value = es.fun_save_messages
        self.meme_switch.value = es.show_meme_on_save
        self.cat_mode_switch.value = es.cat_mode
        self.terminal_mode_switch.value = es.terminal_mode
        self.funny_enabled_switch.value = es.funny_enabled

    def open_settings(self, e: object = None) -> None:
        if not self.settings_overlay.visible:
            self.settings_overlay.visible = True
            self._safe_update(self.settings_overlay)

    def close_settings(self, e: object = None) -> None:
        self.settings_overlay.visible = False
        self._safe_update(self.settings_overlay)

    def update_cat_icons(self) -> None:
        is_cat = self._entertainment.cat_mode
        self.new_project_btn.icon = ft.Icons.PETS if is_cat else ft.Icons.ADD_BOX
        self.delete_project_btn.icon = ft.Icons.PETS if is_cat else ft.Icons.DELETE
        self.settings_btn.icon = ft.Icons.PETS if is_cat else ft.Icons.SETTINGS
        for btn in (self.new_project_btn, self.delete_project_btn, self.settings_btn):
            self._safe_update(btn)
        self._safe_update(self.title_bar)

    def _safe_update(self, control: ft.Control) -> None:
        try:
            control.update()
        except RuntimeError:
            pass

    async def _close_window(self, e: object) -> None:
        await self.page.window.close()
