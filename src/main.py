"""Types Editor - select cfgeconomycore.xml and edit type files."""

from __future__ import annotations

import logging
import os

import flet as ft

from di import create_app_services
from exceptions import YeteeError, ParseError, AccessError
from file_display import FileDisplay
from logging_setup import setup_logging
from services.config_service import ConfigService
from services.entertainment_service import EntertainmentService
from services.settings_service import SettingsService, THEMES, LANGUAGES
from services.update_service import UpdateService

logger = logging.getLogger(__name__)

VERSION = "0.2.2"


class App:
    def __init__(
        self,
        page: ft.Page,
        config_service: ConfigService,
        settings_service: SettingsService,
        update_service: UpdateService,
        entertainment_service: EntertainmentService,
    ) -> None:
        self.page = page
        self.config_path: str | None = None
        self.types_dir: str | None = None
        self._files: dict[str, str] = {}

        self.selected_theme: str = "SYSTEM"
        self.selected_language: str = "English"
        self.check_updates: bool = True

        self._config_service = config_service
        self._settings_service = settings_service
        self._update_service = update_service
        self._entertainment_service = entertainment_service

        page.title = "Yet Another Types Editing Environment | YETEE"
        page.theme_mode = THEMES[self.selected_theme]
        page.on_route_change = self.route_change
        page.on_view_pop = self.view_pop

        self.file_display = FileDisplay(page=self.page, entertainment_service=self._entertainment_service)
        self._build_controls()

        self.file_picker = ft.FilePicker()

        self.route_change()

        self.page.run_task(self._load_settings)

    def _build_controls(self) -> None:
        self.file_dropdown = ft.Dropdown(
            label="File",
            hint_text="Select a file",
            options=[],
            visible=False,
            expand=True,
            on_select=self._on_file_change,
        )
        self.add_btn = ft.Button(
            content=ft.Icon(ft.Icons.ADD),
            style=ft.ButtonStyle(shape=ft.CircleBorder(), padding=10),
            on_click=self._add_file,
            visible=False,
        )
        self.delete_btn = ft.Button(
            content=ft.Row(
                controls=[ft.Icon(ft.Icons.DELETE), ft.Text("Delete")],
                tight=True,
            ),
            style=ft.ButtonStyle(
                bgcolor=ft.Colors.ERROR_CONTAINER,
                color=ft.Colors.ON_ERROR_CONTAINER,
            ),
            on_click=self._on_delete_click,
            visible=False,
        )
        self.selected_dir_text = ft.Text("No config selected", size=14)

        unsupported_yet = ft.AlertDialog(
            modal=True,
            title=ft.Text("WORK IN PROGRESS"),
            content=ft.Text("This feature is not supported yet."),
            actions=[
                ft.TextButton("Dismiss", on_click=lambda e: self.page.pop_dialog()),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        self.start_container = ft.Container(
            width=500,
            expand=True,
            content=ft.Column(
                [
                    ft.Text(
                        "Select cfgeconomycore.xml to start editing type files",
                        size=16,
                        text_align=ft.TextAlign.CENTER,
                    ),
                    ft.Button(
                        "Select local file",
                        icon=ft.Icons.FILE_OPEN,
                        on_click=self._select_config,
                    ),
                    ft.Button(
                        "Select remote file [SSH][WIP]",
                        icon=ft.Icons.WEB,
                        on_click=lambda _: self.page.show_dialog(unsupported_yet),
                    ),
                    ft.Button(
                        "Select remote file [FTP][WIP]",
                        icon=ft.Icons.WEB,
                        on_click=lambda _: self.page.show_dialog(unsupported_yet),
                    )
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                alignment=ft.MainAxisAlignment.CENTER,
                expand=True,
            ),
        )

        self.empty_container = ft.Container(
            expand=True,
            content=ft.Column(
                [
                    ft.Text(
                        "No files in config",
                        size=16,
                        text_align=ft.TextAlign.CENTER,
                    ),
                    ft.Button(
                        content=ft.Icon(ft.Icons.ADD),
                        style=ft.ButtonStyle(shape=ft.CircleBorder(), padding=20),
                        on_click=self._add_file,
                    ),
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                alignment=ft.MainAxisAlignment.CENTER,
                expand=True,
            ),
            visible=False,
        )

        self.editor_container = ft.Column(
            [
                ft.Row([self.selected_dir_text]),
                ft.Row(
                    controls=[self.file_dropdown, self.add_btn, self.delete_btn],
                    alignment=ft.MainAxisAlignment.START,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                self.file_display.control,
            ],
            expand=True,
            visible=False,
        )

        self.content_column = ft.Column(
            controls=[
                self.start_container,
                self.empty_container,
                self.editor_container,
            ],
            alignment=ft.MainAxisAlignment.START,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            expand=True,
        )

    def build_main_view(self) -> ft.View:
        return ft.View(
            route="/",
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                ft.AppBar(
                    title=ft.Text("Types Editor"),
                    bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
                    actions=[
                        ft.IconButton(
                            icon=ft.Icons.SETTINGS,
                            on_click=self.open_settings,
                        ),
                    ],
                ),
                self.content_column,
            ],
        )

    def build_settings_view(self) -> ft.View:
        theme_dropdown = ft.Dropdown(
            label="Theme",
            value=self.selected_theme,
            options=[ft.DropdownOption(key=t) for t in THEMES],
            width=200,
            on_select=self._on_theme_change,
        )

        language_dropdown = ft.Dropdown(
            label="Language",
            value=self.selected_language,
            options=[ft.DropdownOption(key=l) for l in LANGUAGES],
            width=200,
            on_select=self._on_language_change,
        )

        check_updates_switch = ft.Switch(
            value=self.check_updates,
            on_change=self._on_check_updates_change,
        )

        fun_sounds_switch = ft.Switch(
            value=self._entertainment_service.fun_sounds,
            on_change=self._on_fun_sounds_change,
        )
        fun_messages_switch = ft.Switch(
            value=self._entertainment_service.fun_save_messages,
            on_change=self._on_fun_messages_change,
        )
        meme_switch = ft.Switch(
            value=self._entertainment_service.show_meme_on_save,
            on_change=self._on_meme_change,
        )
        cat_mode_switch = ft.Switch(
            value=self._entertainment_service.cat_mode,
            on_change=self._on_cat_mode_change,
        )
        terminal_mode_switch = ft.Switch(
            value=self._entertainment_service.terminal_mode,
            on_change=self._on_terminal_mode_change,
        )
        funny_enabled_switch = ft.Switch(
            value=self._entertainment_service.funny_enabled,
            on_change=self._on_funny_enabled_change,
        )

        return ft.View(
            route="/settings",
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[
                ft.AppBar(
                    title=ft.Text("Settings"),
                    bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
                ),
                ft.Container(
                    width=500,
                    content=ft.Column(
                        [
                            ft.ListTile(
                                title=ft.Text("Theme"),
                                trailing=theme_dropdown,
                                dense=True,
                            ),
                            ft.ListTile(
                                title=ft.Text("Language"),
                                trailing=language_dropdown,
                                dense=True,
                            ),
                            ft.ListTile(
                                title=ft.Text("Check updates on startup"),
                                trailing=check_updates_switch,
                                dense=True,
                            ),
                            ft.Divider(),
                            ft.Text("Entertainment", weight=ft.FontWeight.BOLD, size=14),
                            ft.ListTile(
                                title=ft.Text("Fun sounds (visual effect)"),
                                trailing=fun_sounds_switch,
                                dense=True,
                            ),
                            ft.ListTile(
                                title=ft.Text("Fun save messages"),
                                trailing=fun_messages_switch,
                                dense=True,
                            ),
                            ft.ListTile(
                                title=ft.Text("Show meme on save"),
                                trailing=meme_switch,
                                dense=True,
                            ),
                            ft.ListTile(
                                title=ft.Text("Cat mode"),
                                trailing=cat_mode_switch,
                                dense=True,
                            ),
                            ft.ListTile(
                                title=ft.Text("Terminal mode"),
                                trailing=terminal_mode_switch,
                                dense=True,
                            ),
                            ft.Divider(),
                            ft.Text("Fun Buttons", weight=ft.FontWeight.BOLD, size=14),
                            ft.ListTile(
                                title=ft.Text("Funny setting (show fun buttons)"),
                                trailing=funny_enabled_switch,
                                dense=True,
                            ),
                        ],
                    ),
                ),
            ],
        )

    def route_change(self, route: object = None) -> None:
        self.page.views.clear()
        self.page.views.append(self.build_main_view())
        if self.page.route == "/settings":
            self.page.views.append(self.build_settings_view())
        self.page.update()

    async def view_pop(self, e: ft.ViewPopEvent) -> None:
        if e.view is not None:
            self.page.views.remove(e.view)
            top_view = self.page.views[-1]
            await self.page.push_route(top_view.route)

    async def open_settings(self, e: object) -> None:
        await self.page.push_route("/settings")

    async def _load_settings(self) -> None:
        try:
            settings = await self._settings_service.load_settings()

            theme = settings.get("theme")
            lang = settings.get("language")
            updates = settings.get("check_updates")

            if theme and theme in THEMES:
                self.selected_theme = theme
                self.page.theme_mode = THEMES[theme]

            if lang and lang in LANGUAGES:
                self.selected_language = lang

            if updates is not None:
                assert isinstance(updates, bool)
                self.check_updates = updates

            es = self._entertainment_service
            if "fun_sounds" in settings:
                es.fun_sounds = bool(settings["fun_sounds"])
            if "fun_save_messages" in settings:
                es.fun_save_messages = bool(settings["fun_save_messages"])
            if "show_meme_on_save" in settings:
                es.show_meme_on_save = bool(settings["show_meme_on_save"])
            if "cat_mode" in settings:
                es.cat_mode = bool(settings["cat_mode"])
            if "terminal_mode" in settings:
                es.terminal_mode = bool(settings["terminal_mode"])
            if "funny_enabled" in settings:
                es.funny_enabled = bool(settings["funny_enabled"])
            achievements_raw = settings.get("achievements")
            if isinstance(achievements_raw, str):
                es.achievements_str = achievements_raw

            self.page.update()
            self.file_display._update_funny_visibility()

            if self.check_updates:
                await self._update_service.check_for_updates(VERSION)
        except YeteeError:
            logger.warning("Failed to load settings", exc_info=True)
        except Exception as ex:
            logger.error("Unexpected error loading settings: %s", ex)

    async def _on_theme_change(self, e: ft.ControlEvent) -> None:
        theme = e.control.value
        if theme not in THEMES:
            return
        self.selected_theme = theme
        self.page.theme_mode = THEMES[theme]
        try:
            await self._settings_service.save_setting("theme", theme)
        except Exception as ex:
            logger.error("Failed to save theme setting: %s", ex)
        self.page.update()

    async def _on_language_change(self, e: ft.ControlEvent) -> None:
        lang = e.control.value
        if lang not in LANGUAGES:
            return
        self.selected_language = lang
        try:
            await self._settings_service.save_setting("language", lang)
        except Exception as ex:
            logger.error("Failed to save language setting: %s", ex)
        if lang != "English":
            dialog = ft.AlertDialog(
                title=ft.Text("Not available"),
                content=ft.Text("Language support coming soon."),
                actions=[ft.TextButton("OK", on_click=lambda _: self.page.pop_dialog())],
            )
            self.page.show_dialog(dialog)
        self.page.update()

    async def _on_check_updates_change(self, e: ft.ControlEvent) -> None:
        self.check_updates = e.control.value
        try:
            await self._settings_service.save_setting("check_updates", e.control.value)
        except Exception as ex:
            logger.error("Failed to save check_updates setting: %s", ex)

    async def _on_fun_sounds_change(self, e: ft.ControlEvent) -> None:
        self._entertainment_service.fun_sounds = e.control.value
        try:
            await self._settings_service.save_setting("fun_sounds", e.control.value)
        except Exception as ex:
            logger.error("Failed to save fun_sounds setting: %s", ex)
        if self._entertainment_service.fun_sounds and self._entertainment_service.cat_mode:
            self.file_display._show_meow_popup()

    async def _on_fun_messages_change(self, e: ft.ControlEvent) -> None:
        self._entertainment_service.fun_save_messages = e.control.value
        try:
            await self._settings_service.save_setting("fun_save_messages", e.control.value)
        except Exception as ex:
            logger.error("Failed to save fun_save_messages setting: %s", ex)

    async def _on_meme_change(self, e: ft.ControlEvent) -> None:
        self._entertainment_service.show_meme_on_save = e.control.value
        try:
            await self._settings_service.save_setting("show_meme_on_save", e.control.value)
        except Exception as ex:
            logger.error("Failed to save show_meme_on_save setting: %s", ex)

    async def _on_cat_mode_change(self, e: ft.ControlEvent) -> None:
        self._entertainment_service.cat_mode = e.control.value
        try:
            await self._settings_service.save_setting("cat_mode", e.control.value)
        except Exception as ex:
            logger.error("Failed to save cat_mode setting: %s", ex)
        self.file_display._update_cat_icons()

    async def _on_terminal_mode_change(self, e: ft.ControlEvent) -> None:
        self._entertainment_service.terminal_mode = e.control.value
        try:
            await self._settings_service.save_setting("terminal_mode", e.control.value)
        except Exception as ex:
            logger.error("Failed to save terminal_mode setting: %s", ex)

    async def _on_funny_enabled_change(self, e: ft.ControlEvent) -> None:
        self._entertainment_service.funny_enabled = e.control.value
        try:
            await self._settings_service.save_setting("funny_enabled", e.control.value)
        except Exception as ex:
            logger.error("Failed to save funny_enabled setting: %s", ex)
        self.file_display._update_funny_visibility()

    def _on_file_change(self, e: object) -> None:
        name = self.file_dropdown.value
        if not name or name not in self._files:
            return
        self.delete_btn.visible = True
        self._on_file_click(self._files[name])

    def _on_delete_click(self, e: object) -> None:
        name = self.file_dropdown.value
        if not name:
            return
        self._delete_file(name)

    def _add_file(self, e: object) -> None:
        if not self.config_path:
            return
        self._show_input_dialog("New file name", "my_types.xml")

    def _show_input_dialog(self, title: str, hint: str) -> None:
        name_field = ft.TextField(hint_text=hint, autofocus=True)

        def on_ok(ev: object) -> None:
            name = name_field.value
            self.page.pop_dialog()
            self.page.update()
            if name:
                self._create_file(name)

        def on_cancel(ev: object) -> None:
            self.page.pop_dialog()
            self.page.update()

        name_field.on_submit = on_ok

        dialog = ft.AlertDialog(
            title=ft.Text(title),
            content=name_field,
            actions=[
                ft.TextButton("Cancel", on_click=lambda _: self.page.pop_dialog()),
                ft.TextButton("OK", on_click=lambda _: on_ok(None)),
            ],
        )
        self.page.show_dialog(dialog)

    def _create_file(self, name: str) -> None:
        if not self.config_path:
            return

        try:
            result = self._config_service.create_type_file(self.config_path, name)
            if result is None:
                self.selected_dir_text.value = f"Error creating file: {name}"
                self.page.update()
                return
            self._load_files()
        except YeteeError as ex:
            logger.error("Failed to create file: %s", ex)
            self.selected_dir_text.value = f"Error creating file: {ex}"
            self.page.update()

    def _delete_file(self, name: str) -> None:
        if not self.config_path:
            return

        def on_delete(ev: object) -> None:
            if not self.config_path:
                return
            try:
                success = self._config_service.delete_type_file(self.config_path, name)
                if success:
                    self.file_display.clear()
                    self._load_files()
                else:
                    self.selected_dir_text.value = f"Error deleting file: {name}"
                    self.page.update()
            except YeteeError as ex:
                logger.error("Failed to delete file: %s", ex)
                self.selected_dir_text.value = f"Error deleting file: {ex}"
                self.page.update()
            self.page.pop_dialog()

        def on_cancel(ev: object) -> None:
            self.page.pop_dialog()

        dialog = ft.AlertDialog(
            title=ft.Text("Delete file"),
            content=ft.Text(f"Delete \"{name}\"?"),
            actions=[
                ft.TextButton("Cancel", on_click=on_cancel),
                ft.TextButton("Delete", on_click=on_delete),
            ],
        )
        self.page.show_dialog(dialog)

    def _on_file_click(self, path: str) -> None:
        self.page.run_task(self._load_file_async, path)

    async def _load_file_async(self, path: str) -> None:
        try:
            await self.file_display.load_file_async(path)
        except YeteeError as ex:
            logger.error("Failed to load file: %s", ex)
            self.selected_dir_text.value = f"Error loading file: {ex}"
        except Exception as ex:
            logger.error("Unexpected error loading file: %s", ex)
            self.selected_dir_text.value = f"Unexpected error: {ex}"
        self.page.update()

    def on_open_click(self, e: object) -> None:
        self.page.run_task(self._pick_file)

    async def _pick_file(self) -> None:
        try:
            files = await self.file_picker.pick_files(
                dialog_title="Select cfgeconomycore.xml",
                file_type=ft.FilePickerFileType.CUSTOM,
                allowed_extensions=["xml"],
            )
            if files:
                self.config_path = files[0].path
                self._load_files()
        except Exception as ex:
            logger.error("File picker error: %s", ex)
            self.selected_dir_text.value = f"Error selecting file: {ex}"
            self.page.update()

    def _load_files(self) -> None:
        if not self.config_path:
            return

        self._files.clear()
        self.selected_dir_text.value = f"Config: {self.config_path}"

        try:
            filenames = self._config_service.load_files(self.config_path)
            self.types_dir = self._config_service.get_types_dir(self.config_path)
            if self.types_dir:
                for name in filenames:
                    self._files[name] = os.path.join(self.types_dir, name)
        except YeteeError as ex:
            logger.error("Error loading files from config: %s", ex)
            self.selected_dir_text.value = f"Error parsing config: {ex}"
            self.page.update()
            return
        except Exception as ex:
            logger.error("Unexpected error: %s", ex)
            self.selected_dir_text.value = f"Error parsing config: {ex}"
            self.page.update()
            return

        self.file_dropdown.options = [
            ft.DropdownOption(key=name) for name in self._files
        ]
        if self._files:
            first_name = next(iter(self._files))
            self.file_dropdown.value = first_name
            self.file_dropdown.visible = True
            self.add_btn.visible = True
            self.delete_btn.visible = True
            self.file_display.clear()
            self.empty_container.visible = False
            self.editor_container.visible = True
            self._on_file_click(self._files[first_name])
        else:
            self.file_dropdown.value = None
            self.file_dropdown.visible = False
            self.add_btn.visible = False
            self.delete_btn.visible = False
            self.file_display.clear()
            self.editor_container.visible = False
            self.empty_container.visible = True

        self.start_container.visible = False
        self.page.update()

    def _select_config(self, e: object) -> None:
        self.page.run_task(self._pick_file)


def main(page: ft.Page) -> None:
    setup_logging()
    services = create_app_services(page)
    App(
        page=page,
        config_service=services["config_service"],
        settings_service=services["settings_service"],
        update_service=services["update_service"],
        entertainment_service=services["entertainment_service"],
    )
    page.update()


if __name__ == "__main__":
    ft.app(target=main)
