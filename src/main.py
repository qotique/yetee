from __future__ import annotations

import logging
import os

import flet as ft

from di import create_app_services
from exceptions import YeteeError, ParseError, AccessError
from logging_setup import setup_logging
from models.project import Project
from services.config_service import ConfigService
from services.economy_service import EconomyService
from services.entertainment_service import EntertainmentService
from services.project_service import ProjectService
from services.settings_service import SettingsService, THEMES, LANGUAGES
from services.update_service import UpdateService
from ui.economy_editor import EconomyEditor

logger = logging.getLogger(__name__)

VERSION = "0.4.1"


class App:
    def __init__(
        self,
        page: ft.Page,
        config_service: ConfigService,
        settings_service: SettingsService,
        update_service: UpdateService,
        entertainment_service: EntertainmentService,
        project_service: ProjectService,
        economy_editor: EconomyEditor,
    ) -> None:
        self.page = page
        self._config_service = config_service
        self._settings_service = settings_service
        self._update_service = update_service
        self._entertainment_service = entertainment_service
        self._project_service = project_service
        self._economy_editor = economy_editor

        self.selected_theme: str = "SYSTEM"
        self.selected_language: str = "English"
        self.check_updates: bool = True

        page.title = "Yet Another Types Editing Environment | YETEE"
        page.window.title_bar_hidden = True
        page.window.maximized = True
        page.theme_mode = THEMES[self.selected_theme]
        page.on_route_change = self.route_change
        page.on_view_pop = self.view_pop

        self._build_controls()
        self.route_change()
        self.page.update()
        self.page.run_task(self._load_settings)

    def _build_controls(self) -> None:
        self._project_dropdown = ft.Dropdown(
            label="Project",
            options=[],
            text_size=12,
            width=200,
            dense=True,
            content_padding=ft.Padding(4, 0, 4, 0),
            on_select=self._on_project_switch,
        )
        self._delete_project_btn = ft.IconButton(
            icon=ft.Icons.DELETE,
            tooltip="Delete current project",
            visible=False,
            on_click=self._on_delete_project,
        )
        self._new_project_btn = ft.IconButton(
            icon=ft.Icons.ADD_BOX,
            tooltip="New Project",
            on_click=self._show_new_project_dialog,
        )
        self._entity_dropdown = ft.Dropdown(
            label="Entity",
            text_size=12,
            options=[],
            width=170,
            dense=True,
            content_padding=ft.Padding(4, 0, 4, 0),
            visible=False,
            on_select=self._on_entity_switch,
        )
        self._save_btn = ft.Button(
            "Save",
            icon=ft.Icons.SAVE,
            on_click=self._on_save,
            visible=False,
        )

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
                    ft.Button(
                        "New Project",
                        icon=ft.Icons.ADD_BOX,
                        on_click=self._show_new_project_dialog,
                    ),
                    ft.Button(
                        "Open Project",
                        icon=ft.Icons.FILE_OPEN,
                        on_click=self._show_open_project_dialog,
                    ),
                    ft.Divider(
                        height=10,
                        color=ft.Colors.TRANSPARENT,
                    ),
                    ft.Text(
                        "Quick start:",
                        size=12,
                        italic=True,
                        color=ft.Colors.GREY_500,
                    ),
                    ft.Button(
                        "Select economy directory",
                        icon=ft.Icons.FOLDER_OPEN,
                        on_click=self._select_economy_dir,
                    ),
                ],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                alignment=ft.MainAxisAlignment.CENTER,
                expand=True,
            ),
        )

        self.content_column = ft.Column(
            controls=[
                self.start_container,
                self._economy_editor.control,
            ],
            alignment=ft.MainAxisAlignment.START,
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            expand=True,
        )

        self._settings_btn = ft.IconButton(
            icon=ft.Icons.SETTINGS,
            on_click=self.open_settings,
        )

        self._theme_dropdown = ft.Dropdown(
            label="Theme",
            value=self.selected_theme,
            options=[ft.DropdownOption(key=t) for t in THEMES],
            width=200,
            on_select=self._on_theme_change,
        )
        self._language_dropdown = ft.Dropdown(
            label="Language",
            value=self.selected_language,
            options=[ft.DropdownOption(key=l) for l in LANGUAGES],
            width=200,
            on_select=self._on_language_change,
        )
        self._check_updates_switch = ft.Switch(
            value=self.check_updates,
            on_change=self._on_check_updates_change,
        )
        self._fun_messages_switch = ft.Switch(
            value=self._entertainment_service.fun_save_messages,
            on_change=self._on_fun_messages_change,
        )
        self._meme_switch = ft.Switch(
            value=self._entertainment_service.show_meme_on_save,
            on_change=self._on_meme_change,
        )
        self._cat_mode_switch = ft.Switch(
            value=self._entertainment_service.cat_mode,
            on_change=self._on_cat_mode_change,
        )
        self._terminal_mode_switch = ft.Switch(
            value=self._entertainment_service.terminal_mode,
            on_change=self._on_terminal_mode_change,
        )
        self._funny_enabled_switch = ft.Switch(
            value=self._entertainment_service.funny_enabled,
            on_change=self._on_funny_enabled_change,
        )

        self._settings_overlay = ft.Container(
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
                                    on_click=self._close_settings,
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
                                    trailing=self._theme_dropdown,
                                    dense=True,
                                ),
                                ft.ListTile(
                                    title=ft.Text("Language"),
                                    trailing=self._language_dropdown,
                                    dense=True,
                                ),
                                ft.ListTile(
                                    title=ft.Text("Check updates on startup"),
                                    trailing=self._check_updates_switch,
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
                                    trailing=self._fun_messages_switch,
                                    dense=True,
                                ),
                                ft.ListTile(
                                    title=ft.Text("Show meme on save"),
                                    trailing=self._meme_switch,
                                    dense=True,
                                ),
                                ft.ListTile(
                                    title=ft.Text("Cat mode"),
                                    trailing=self._cat_mode_switch,
                                    dense=True,
                                ),
                                ft.ListTile(
                                    title=ft.Text("Terminal mode"),
                                    trailing=self._terminal_mode_switch,
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
                                    trailing=self._funny_enabled_switch,
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

        self._title_bar = ft.Container(
            content=ft.WindowDragArea(
                content=ft.Row(
                    [
                        ft.Container(expand=True),
                        self._entity_dropdown,
                        self._project_dropdown,
                        self._new_project_btn,
                        self._delete_project_btn,
                        self._settings_btn,
                        ft.IconButton(
                            icon=ft.Icons.CLOSE,
                            on_click=self._close_window,
                        ),
                    ],
                    spacing=2,
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                maximizable=True,
            ),
            bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
            height=56,
            padding=ft.Padding(left=0, top=0, right=4, bottom=0),
        )

        self._content_stack = ft.Stack(
            controls=[
                self.content_column,
                self._settings_overlay,
            ],
            expand=True,
        )

    def build_main_view(self) -> ft.View:
        return ft.View(
            route="/",
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            controls=[self._title_bar, self._content_stack],
        )

    async def _close_window(self, e: object) -> None:
        await self.page.window.close()

    def _close_settings(self, e: object = None) -> None:
        self._settings_overlay.visible = False
        try:
            self._settings_overlay.update()
        except RuntimeError:
            pass

    def _sync_settings_to_controls(self) -> None:
        self._theme_dropdown.value = self.selected_theme
        self._language_dropdown.value = self.selected_language
        self._check_updates_switch.value = self.check_updates
        self._fun_messages_switch.value = self._entertainment_service.fun_save_messages
        self._meme_switch.value = self._entertainment_service.show_meme_on_save
        self._cat_mode_switch.value = self._entertainment_service.cat_mode
        self._terminal_mode_switch.value = self._entertainment_service.terminal_mode
        self._funny_enabled_switch.value = self._entertainment_service.funny_enabled

    def route_change(self, route: object = None) -> None:
        if not hasattr(self, "_title_bar"):
            return
        if not self.page.views or not self.page.views[0].controls:
            self.page.views.clear()
            self.page.views.append(self.build_main_view())

    async def view_pop(self, e: ft.ViewPopEvent) -> None:
        if self._settings_overlay.visible:
            self._close_settings()

    async def open_settings(self, e: object) -> None:
        if not self._settings_overlay.visible:
            self._sync_settings_to_controls()
            self._settings_overlay.visible = True
            try:
                self._settings_overlay.update()
            except RuntimeError:
                pass

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
            if "fun_save_messages" in settings:
                es.fun_save_messages = bool(settings["fun_save_messages"])
            if "show_meme_on_save" in settings:
                es.show_meme_on_save = bool(settings["show_meme_on_save"])
            if "cat_mode" in settings:
                es.cat_mode = bool(settings["cat_mode"])
                self._update_appbar_cat_icons()
            if "terminal_mode" in settings:
                es.terminal_mode = bool(settings["terminal_mode"])
            if "funny_enabled" in settings:
                es.funny_enabled = bool(settings["funny_enabled"])
            achievements_raw = settings.get("achievements")
            if isinstance(achievements_raw, str):
                es.achievements_str = achievements_raw
            self.page.update()
            if self.check_updates:
                await self._update_service.check_for_updates(VERSION)
        except YeteeError:
            logger.warning("Failed to load settings", exc_info=True)
        except Exception as ex:
            logger.error("Unexpected error loading settings: %s", ex)

        self._refresh_project_dropdown()
        last = self._project_service.get_last_project()
        if last is not None and os.path.isdir(last.economy_dir):
            self._open_project(last)
        self.page.update()

    def _refresh_project_dropdown(self) -> None:
        projects = self._project_service.load_projects()
        self._project_dropdown.options = [
            ft.DropdownOption(key=p.name) for p in projects
        ]
        if self._economy_editor.project is not None:
            self._project_dropdown.value = self._economy_editor.project.name
        elif projects:
            self._project_dropdown.value = projects[-1].name
        try:
            self._project_dropdown.update()
        except RuntimeError:
            pass

    def _open_project(self, project: Project) -> None:
        self._project_service.mark_opened(project)
        self._economy_editor.control.visible = True
        self._economy_editor.load_project(project)
        self.start_container.visible = False
        self._save_btn.visible = True
        self._delete_project_btn.visible = True
        self._refresh_project_dropdown()
        self._refresh_selectors()
        self._update_appbar_cat_icons()
        self.page.update()

    def _show_new_project_dialog(self, e: object = None) -> None:
        name_field = ft.TextField(
            label="Project name",
            hint_text="MyServer",
            autofocus=True,
        )
        economy_dir_field = ft.TextField(
            label="Economy directory",
            hint_text="/path/to/mpmissions/<map_name>",
            expand=True,
        )
        profiles_dir_field = ft.TextField(
            label="Profiles directory (optional)",
            hint_text="/path/to/profiles",
            expand=True,
        )

        async def pick_economy_dir(ev: object) -> None:
            path = await ft.FilePicker().get_directory_path(
                dialog_title="Select economy directory (mpmissions/<map_name>)",
            )
            if path:
                economy_dir_field.value = path
                economy_dir_field.update()

        async def pick_profiles_dir(ev: object) -> None:
            path = await ft.FilePicker().get_directory_path(
                dialog_title="Select profiles directory",
            )
            if path:
                profiles_dir_field.value = path
                profiles_dir_field.update()

        def create(ev: object) -> None:
            name = name_field.value
            economy_dir = economy_dir_field.value
            if not name or not economy_dir:
                return
            if not os.path.isdir(economy_dir):
                logger.warning("Economy directory does not exist: %s", economy_dir)
                return
            self.page.pop_dialog()
            self.page.update()
            self._create_project(name, economy_dir, profiles_dir_field.value or "")

        def cancel(ev: object) -> None:
            self.page.pop_dialog()
            self.page.update()

        browse_economy_btn = ft.IconButton(
            icon=ft.Icons.FOLDER_OPEN, on_click=pick_economy_dir
        )
        browse_profiles_btn = ft.IconButton(
            icon=ft.Icons.FOLDER_OPEN, on_click=pick_profiles_dir
        )

        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("New Project"),
            content=ft.Column(
                [
                    name_field,
                    ft.Row([economy_dir_field, browse_economy_btn], spacing=4),
                    ft.Row([profiles_dir_field, browse_profiles_btn], spacing=4),
                ],
                tight=True,
                width=500,
            ),
            actions=[
                ft.TextButton("Cancel", on_click=cancel),
                ft.TextButton("Create", on_click=create),
            ],
        )
        self.page.show_dialog(dialog)
        self.page.update()

    def _create_project(
        self, name: str, economy_dir: str, profiles_dir: str = ""
    ) -> None:
        try:
            svc = EconomyService()
            types_dir = svc.get_types_dir(economy_dir)
            project = Project(
                name=name,
                economy_dir=economy_dir,
                types_dir=types_dir,
                profiles_dir=profiles_dir,
            )
            self._project_service.add_project(project)
            self._open_project(project)
        except (YeteeError, Exception) as ex:
            logger.error("Failed to create project: %s", ex)
            dialog = ft.AlertDialog(
                title=ft.Text("Error"),
                content=ft.Text(f"Failed to create project: {ex}"),
                actions=[
                    ft.TextButton(
                        "OK",
                        on_click=lambda _: self.page.pop_dialog(),
                    )
                ],
            )
            self.page.show_dialog(dialog)
            self.page.update()

    def _show_open_project_dialog(self, e: object = None) -> None:
        projects = self._project_service.load_projects()
        if not projects:
            dialog = ft.AlertDialog(
                title=ft.Text("No Projects"),
                content=ft.Text("No saved projects found. Create a new project first."),
                actions=[
                    ft.TextButton(
                        "OK",
                        on_click=lambda _: self.page.pop_dialog(),
                    )
                ],
            )
            self.page.show_dialog(dialog)
            self.page.update()
            return

        options = [ft.DropdownOption(key=p.name) for p in projects]
        dropdown = ft.Dropdown(
            label="Select project",
            options=options,
            autofocus=True,
        )

        def do_open(ev: object) -> None:
            name = dropdown.value
            if not name:
                return
            project = self._project_service.get_project(name)
            if project is None:
                return
            self.page.pop_dialog()
            self.page.update()
            self._open_project(project)

        def do_delete(ev: object) -> None:
            name = dropdown.value
            if not name:
                return
            self._project_service.remove_project(name)
            self._refresh_project_dropdown()
            self.page.pop_dialog()
            self._show_open_project_dialog()

        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("Open Project"),
            content=dropdown,
            actions=[
                ft.TextButton("Delete", on_click=do_delete),
                ft.TextButton("Cancel", on_click=lambda _: self.page.pop_dialog()),
                ft.TextButton("Open", on_click=do_open),
            ],
        )
        self.page.show_dialog(dialog)
        self.page.update()

    def _on_project_switch(self, e: object) -> None:
        name = self._project_dropdown.value
        if not name:
            return
        project = self._project_service.get_project(name)
        if project is not None:
            self._economy_editor.save_file()
            self._open_project(project)

    def _on_delete_project(self, e: object) -> None:
        project = self._economy_editor.project
        if project is None:
            return

        def confirm(ev: object) -> None:
            self.page.pop_dialog()
            self._project_service.remove_project(project.name)
            self._economy_editor.unload()
            self._economy_editor.control.visible = False
            self._delete_project_btn.visible = False
            self._save_btn.visible = False
            self.start_container.visible = True
            self._refresh_project_dropdown()
            self._refresh_selectors()
            self.page.update()

        def cancel(ev: object) -> None:
            self.page.pop_dialog()

        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("Delete Project"),
            content=ft.Text(
                f'Delete project "{project.name}"?\nThis does not delete any files.'
            ),
            actions=[
                ft.TextButton("Cancel", on_click=cancel),
                ft.TextButton("Delete", on_click=confirm),
            ],
        )
        self.page.show_dialog(dialog)
        self.page.update()

    def _refresh_selectors(self) -> None:
        entities = self._economy_editor.available_entities
        if entities:
            self._entity_dropdown.options = [ft.DropdownOption(key=e) for e in entities]
            self._entity_dropdown.value = self._economy_editor.current_entity
            self._entity_dropdown.visible = len(entities) > 1
        else:
            self._entity_dropdown.options = []
            self._entity_dropdown.visible = False
        try:
            self._entity_dropdown.update()
        except RuntimeError:
            pass

    def _on_entity_switch(self, e: object) -> None:
        entity = self._entity_dropdown.value
        if entity:
            self._economy_editor.switch_entity(entity)
            self._refresh_selectors()

    def _on_save(self, e: object) -> None:
        self._economy_editor.save_current(e)

    async def _select_economy_dir(self, e: object) -> None:
        path = await ft.FilePicker().get_directory_path(
            dialog_title="Select economy directory (mpmissions/<map_name>)",
        )
        if not path:
            return
        name = os.path.basename(path)
        if not name or name == "":
            name = "MyProject"
        self._create_project(name, path)

    async def _save_setting(self, key: str, value: object) -> None:
        try:
            await self._settings_service.save_setting(key, value)
        except Exception as ex:
            logger.error("Failed to save %s setting: %s", key, ex)

    async def _on_theme_change(self, e: ft.ControlEvent) -> None:
        theme = e.control.value
        if theme not in THEMES:
            return
        self.selected_theme = theme
        self.page.theme_mode = THEMES[theme]
        await self._save_setting("theme", theme)
        self.page.update()

    async def _on_language_change(self, e: ft.ControlEvent) -> None:
        lang = e.control.value
        if lang not in LANGUAGES:
            return
        self.selected_language = lang
        await self._save_setting("language", lang)
        if lang != "English":
            dialog = ft.AlertDialog(
                title=ft.Text("Not available"),
                content=ft.Text("Language support coming soon."),
                actions=[
                    ft.TextButton(
                        "OK",
                        on_click=lambda _: self.page.pop_dialog(),
                    )
                ],
            )
            self.page.show_dialog(dialog)
        self.page.update()

    async def _on_check_updates_change(self, e: ft.ControlEvent) -> None:
        self.check_updates = e.control.value
        await self._save_setting("check_updates", e.control.value)

    async def _on_fun_messages_change(self, e: ft.ControlEvent) -> None:
        self._entertainment_service.fun_save_messages = e.control.value
        await self._save_setting("fun_save_messages", e.control.value)

    async def _on_meme_change(self, e: ft.ControlEvent) -> None:
        self._entertainment_service.show_meme_on_save = e.control.value
        await self._save_setting("show_meme_on_save", e.control.value)

    async def _on_cat_mode_change(self, e: ft.ControlEvent) -> None:
        self._entertainment_service.cat_mode = e.control.value
        await self._save_setting("cat_mode", e.control.value)
        self._economy_editor.file_display.update_cat_icons()
        self._economy_editor.event_display.update_cat_icons()
        self._update_appbar_cat_icons()
        self.page.update()

    def _update_appbar_cat_icons(self) -> None:
        is_cat = self._entertainment_service.cat_mode
        self._new_project_btn.icon = ft.Icons.PETS if is_cat else ft.Icons.ADD_BOX
        self._delete_project_btn.icon = ft.Icons.PETS if is_cat else ft.Icons.DELETE
        self._settings_btn.icon = ft.Icons.PETS if is_cat else ft.Icons.SETTINGS
        self._new_project_btn.update()
        self._delete_project_btn.update()
        self._settings_btn.update()
        self._title_bar.update()

    async def _on_terminal_mode_change(self, e: ft.ControlEvent) -> None:
        self._entertainment_service.terminal_mode = e.control.value
        await self._save_setting("terminal_mode", e.control.value)

    async def _on_funny_enabled_change(self, e: ft.ControlEvent) -> None:
        self._entertainment_service.funny_enabled = e.control.value
        await self._save_setting("funny_enabled", e.control.value)
        self._economy_editor.file_display.update_funny_visibility()


def main(page: ft.Page) -> None:
    setup_logging()
    services = create_app_services(page)
    App(
        page=page,
        config_service=services["config_service"],
        settings_service=services["settings_service"],
        update_service=services["update_service"],
        entertainment_service=services["entertainment_service"],
        project_service=services["project_service"],
        economy_editor=services["economy_editor"],
    )
    page.update()


if __name__ == "__main__":
    ft.run(main=main)
