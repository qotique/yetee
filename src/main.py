from __future__ import annotations

import asyncio
import logging
import os
import time
from collections.abc import Callable

import flet as ft

import expansion  # noqa: F401  (registers Expansion schemas at import)
from di import create_app_services
from exceptions import YeteeError
from logging_setup import setup_logging
from models.connection import ConnectionConfig
from models.project import Project
from mod_handlers import not_yet_available_entities
from services.config_service import ConfigService
from services.connection_manager import ConnectionManager
from services.economy_service import EconomyService
from services.entertainment_service import EntertainmentService
from services.profile_service import ProfileService
from services.profile_preload_service import estimate_preload, should_confirm
from services.project_service import ProjectService
from services.remote_sync_service import RemoteSyncService
from services.settings_service import SettingsService, THEMES, LANGUAGES
from services.update_service import UpdateService
from settings_table_display import SettingsTableDisplay
from ui.economy_editor import EconomyEditor

logger = logging.getLogger(__name__)

VERSION = "0.6.1"


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
        connection_manager: ConnectionManager | None = None,
        remote_sync_service: RemoteSyncService | None = None,
        profile_service: ProfileService | None = None,
    ) -> None:
        self.page = page
        self._config_service = config_service
        self._settings_service = settings_service
        self._update_service = update_service
        self._entertainment_service = entertainment_service
        self._project_service = project_service
        self._economy_editor = economy_editor
        self._connection_manager = connection_manager or ConnectionManager()
        self._remote_sync = remote_sync_service or RemoteSyncService(
            self._connection_manager
        )
        self._profile_service = profile_service or ProfileService()
        self._connections_protocol: str = "ssh"

        self._economy_editor.file_display.on_saved = self._on_local_saved
        self._economy_editor.event_display.on_saved = self._on_local_saved
        if self._economy_editor.settings_display is not None:
            self._economy_editor.settings_display.on_saved = self._on_local_saved
        if self._economy_editor.form_display is not None:
            self._economy_editor.form_display.on_saved = self._on_local_saved

        self.selected_theme: str = "SYSTEM"
        self.selected_language: str = "English"
        self.check_updates: bool = True
        self.show_unhandled_mod_editors: bool = False

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
        self._refresh_btn = ft.IconButton(
            icon=ft.Icons.REFRESH,
            tooltip="Refresh project",
            visible=False,
            on_click=self._on_refresh_project,
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
                        "Connect via SSH",
                        icon=ft.Icons.LAN,
                        on_click=lambda _: self._show_connections_dialog(
                            protocol="ssh"
                        ),
                    ),
                    ft.Button(
                        "Connect via FTP",
                        icon=ft.Icons.CLOUD,
                        on_click=lambda _: self._show_connections_dialog(
                            protocol="ftp"
                        ),
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
        self._unhandled_editors_switch = ft.Switch(
            value=self.show_unhandled_mod_editors,
            on_change=self._on_unhandled_editors_change,
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
                                ft.ListTile(
                                    title=ft.Text("Edit all mods [BETA]"),
                                    trailing=self._unhandled_editors_switch,
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
                        self._refresh_btn,
                        self._settings_btn,
                        ft.IconButton(
                            icon=ft.Icons.SWAP_VERT_CIRCLE,
                            tooltip="Connections",
                            on_click=self._show_connections_dialog,
                        ),
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
        self._unhandled_editors_switch.value = self.show_unhandled_mod_editors

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
            if "show_unhandled_mod_editors" in settings:
                self.show_unhandled_mod_editors = bool(
                    settings["show_unhandled_mod_editors"]
                )
                self._economy_editor.set_show_unhandled_editors(
                    self.show_unhandled_mod_editors
                )
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
        self._refresh_btn.visible = True
        self._refresh_project_dropdown()
        self._refresh_selectors()
        self._update_appbar_cat_icons()
        self.page.update()
        self._preload_profile_files(project, confirm=False)

    def _preload_profile_files(self, project: Project, *, confirm: bool) -> None:
        if not project.profiles_dir:
            return
        settings_display = self._economy_editor.settings_display
        if settings_display is None:
            return
        scanned = self._profile_service.scan_profiles(project.profiles_dir)
        files = sorted(
            path
            for entity, paths in scanned.items()
            if self._economy_editor.is_editable_entity(entity)
            for path in paths.values()
        )
        if not files:
            return
        estimate = estimate_preload(files)
        if not confirm or not should_confirm(estimate):
            self.page.run_task(settings_display.preload_cached, files)
            return
        self._show_profile_preload_dialog(files, estimate)

    def _show_profile_preload_dialog(self, files: list[str], estimate: object) -> None:
        settings_display = self._economy_editor.settings_display
        if settings_display is None:
            return
        count = getattr(estimate, "count", len(files))
        seconds = getattr(estimate, "seconds", 0.0)
        info_text = ft.Text(
            f"{count} profile files… estimated ~{seconds:.1f}s to load",
            size=14,
        )
        progress = ft.ProgressBar(value=None, expand=True)
        progress_text = ft.Text("0/0", size=12)
        progress_row = ft.Row([progress, progress_text], spacing=8, visible=False)
        cancelled = {"value": False}

        def cancel_load(e: object) -> None:
            cancelled["value"] = True
            self.page.pop_dialog()
            self.page.update()

        def start_load(e: object) -> None:
            actions_row.visible = False
            progress_row.visible = True
            self.page.update()
            self.page.run_task(
                self._run_preload,
                files,
                cancelled,
                progress,
                progress_text,
                settings_display,
            )

        actions_row = ft.Row(
            [
                ft.TextButton("OK", on_click=start_load),
                ft.TextButton("Cancel", on_click=cancel_load),
            ],
            alignment=ft.MainAxisAlignment.END,
        )
        content = ft.Column(
            [info_text, actions_row, progress_row],
            tight=True,
            width=420,
        )
        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("Loading profiles"),
            content=content,
        )
        self.page.show_dialog(dialog)
        self.page.update()

    async def _run_preload(
        self,
        files: list[str],
        cancelled: dict[str, bool],
        progress: ft.ProgressBar,
        progress_text: ft.Text,
        settings_display: SettingsTableDisplay,
    ) -> None:
        total = len(files)

        def on_progress(done: int, total: int) -> None:
            progress.value = done / total if total else 0
            progress_text.value = f"{done}/{total}"
            progress.update()
            progress_text.update()

        def cancel_check() -> bool:
            return cancelled["value"]

        try:
            await settings_display.preload_cached(
                files, on_progress=on_progress, cancel_check=cancel_check
            )
        except Exception as ex:  # noqa: BLE001
            logger.exception("Profile preload failed unexpectedly")
            progress.value = None
            progress_text.value = f"Error: {ex}"
            progress.update()
            progress_text.update()
            await asyncio.sleep(1.5)
        finally:
            self.page.pop_dialog()
            self.page.update()

    def _show_new_project_dialog(
        self,
        e: object = None,
        name: str = "",
        economy_dir: str = "",
        profiles_dir: str = "",
    ) -> None:
        name_field = ft.TextField(
            label="Project name",
            hint_text="MyServer",
            value=name,
            autofocus=True,
        )
        economy_dir_field = ft.TextField(
            label="Economy directory",
            hint_text="/path/to/mpmissions/<map_name>",
            value=economy_dir,
            expand=True,
        )
        profiles_dir_field = ft.TextField(
            label="Profiles directory (optional)",
            hint_text="/path/to/profiles",
            value=profiles_dir,
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
            self._create_project(
                name,
                economy_dir,
                profiles_dir_field.value or "",
            )

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
                    ft.Divider(height=12),
                    ft.Row(
                        [
                            ft.Text("Add a remote project:", size=12, italic=True),
                            ft.TextButton(
                                "via SSH...",
                                on_click=lambda _: self._show_connections_dialog(
                                    protocol="ssh"
                                ),
                            ),
                            ft.TextButton(
                                "via FTP...",
                                on_click=lambda _: self._show_connections_dialog(
                                    protocol="ftp"
                                ),
                            ),
                        ],
                        alignment=ft.MainAxisAlignment.CENTER,
                    ),
                ],
                tight=True,
                width=520,
            ),
            actions=[
                ft.TextButton("Cancel", on_click=cancel),
                ft.TextButton("Create", on_click=create),
            ],
        )
        self.page.show_dialog(dialog)
        self.page.update()

    def _create_project(
        self,
        name: str,
        economy_dir: str,
        profiles_dir: str = "",
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
            self._refresh_btn.visible = False
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
        self._on_local_saved()

    def _on_local_saved(self) -> None:
        project = self._economy_editor.project
        if project is None or not project.is_remote or not project.connection_id:
            return
        cfg = self._connection_manager.get(project.connection_id)
        if cfg is None:
            print("[diag save] no connection config found, skip upload")
            return
        print(
            f"[diag save] local saved; scheduling upload to "
            f"{project.remote_dir or cfg.remote_economy_dir}"
        )
        profiles_dir = (
            project.profiles_dir
            if cfg.remote_profiles_dir and project.profiles_dir
            else ""
        )
        try:
            self.page.run_task(
                self._upload_remote,
                cfg,
                project.economy_dir,
                project.remote_dir or cfg.remote_economy_dir,
                profiles_dir,
                cfg.remote_profiles_dir if profiles_dir else "",
            )
        except RuntimeError as ex:
            print(f"[diag save] run_task error: {ex!r}")

    def _on_refresh_project(self, e: object) -> None:
        project = self._economy_editor.project
        if project is None:
            return
        if project.is_remote and project.connection_id:
            cfg = self._connection_manager.get(project.connection_id)
            if cfg is None:
                self._show_error("Connection not found for refresh.")
                return
            self.page.run_task(self._refresh_remote_project, cfg, project)
        else:
            self.page.run_task(self._refresh_local_project, project)

    async def _refresh_local_project(self, project: Project) -> None:
        self._economy_editor.load_project(project)
        self._refresh_selectors()
        self.page.update()
        self._preload_profile_files(project, confirm=True)

    async def _refresh_remote_project(
        self, cfg: ConnectionConfig, project: Project
    ) -> None:
        remote_dir = project.remote_dir or cfg.remote_economy_dir
        if not remote_dir:
            self._show_error("Set the remote economy directory first.")
            return
        local_profiles = project.profiles_dir if cfg.remote_profiles_dir else ""
        sync_progress = ft.ProgressBar(value=0, expand=True)
        sync_progress_text = ft.Text("… connecting", size=12)
        sync_dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("Refreshing project"),
            content=ft.Column(
                [
                    ft.Text(
                        f"Syncing files from {cfg.host}:{cfg.port}",
                        size=14,
                    ),
                    ft.Row([sync_progress]),
                    sync_progress_text,
                ],
                tight=True,
                width=420,
            ),
        )
        self.page.show_dialog(sync_dialog)
        self.page.update()
        started = time.monotonic()
        try:
            await self._remote_sync.sync_to_local(
                cfg,
                remote_dir,
                project.economy_dir,
                remote_profiles_dir=cfg.remote_profiles_dir,
                local_profiles_dir=local_profiles if local_profiles else "",
                exclude_profiles=not_yet_available_entities(),
                on_progress=self._make_sync_progress(
                    sync_progress, sync_progress_text, started
                ),
            )
        except YeteeError as ex:
            self.page.pop_dialog()
            self._show_error(f"Failed to refresh project: {ex}")
            return
        except ValueError as ex:
            self.page.pop_dialog()
            self._show_error(str(ex))
            return
        except Exception as ex:  # noqa: BLE001
            self.page.pop_dialog()
            self._show_error(f"Failed to refresh project: {ex}")
            return
        self.page.pop_dialog()
        self._economy_editor.load_project(project)
        self._refresh_selectors()
        self.page.update()
        self._preload_profile_files(project, confirm=True)

    async def _upload_remote(
        self,
        cfg: ConnectionConfig,
        local_dir: str,
        remote_dir: str,
        local_profiles_dir: str = "",
        remote_profiles_dir: str = "",
    ) -> None:
        print(f"[diag save] _upload_remote start: {local_dir} -> {remote_dir}")
        try:
            await self._remote_sync.upload_to_remote(
                cfg,
                local_dir,
                remote_dir,
                local_profiles_dir=local_profiles_dir,
                remote_profiles_dir=remote_profiles_dir,
                exclude_profiles=not_yet_available_entities(),
            )
            print("[diag save] UPLOAD OK")
        except Exception as ex:  # noqa: BLE001
            print(f"[diag save] UPLOAD FAILED: {type(ex).__name__}: {ex!r}")

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

    def _show_connections_dialog(
        self, e: object = None, protocol: str | None = None
    ) -> None:
        if protocol is not None:
            self._connections_protocol = protocol
        connections = [
            c
            for c in self._connection_manager.list_connections()
            if c.protocol == self._connections_protocol
        ]
        if not connections:
            hint = ft.Text(
                f"No {self._connections_protocol.upper()} connections yet. "
                f"Click Add to connect to a server over "
                f"{self._connections_protocol.upper()}.",
                color=ft.Colors.GREY_500,
            )
        else:
            hint = None

        rows: list[ft.Control] = []
        for index, cfg in enumerate(connections):
            label = cfg.project_name or cfg.host
            title = f"{label} · {cfg.host}:{cfg.port} ({cfg.username})"
            subtitle = f"Remote dir: {cfg.remote_economy_dir or 'not set'} | Profiles: {cfg.remote_profiles_dir or 'not set'}"

            async def open_remote(_e: object, c: ConnectionConfig = cfg) -> None:
                await self._open_remote_project(c)

            async def test_conn(_e: object, c: ConnectionConfig = cfg) -> None:
                print(f"[diag] Test button clicked for {c.protocol} {c.host}:{c.port}")
                await self._test_connection(c)

            del_btn = ft.TextButton(
                "Delete",
                on_click=lambda _e, c=cfg: self._delete_connection(c),
            )
            open_btn = ft.TextButton(
                "Open remote",
                disabled=not cfg.remote_economy_dir,
                on_click=open_remote,
            )
            test_btn = ft.TextButton("Test", on_click=test_conn)
            item = ft.Row(
                [
                    ft.Column(
                        [
                            ft.Text(title, size=13, expand=True),
                            ft.Text(
                                subtitle,
                                size=11,
                                color=ft.Colors.ON_SURFACE_VARIANT,
                            ),
                        ],
                        expand=True,
                        spacing=1,
                    ),
                    ft.Row([test_btn, open_btn, del_btn], spacing=2),
                ],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            )
            rows.append(item)
            if index < len(connections) - 1:
                rows.append(ft.Divider(height=1))

        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text(f"{self._connections_protocol.upper()} Connections"),
            content=ft.Column(
                [hint] + rows if hint else rows,
                scroll=ft.ScrollMode.AUTO,
                width=560,
            ),
            actions=[
                ft.TextButton(
                    "Add",
                    on_click=self._show_add_connection_dialog,
                ),
                ft.TextButton("Close", on_click=lambda _: self.page.pop_dialog()),
            ],
        )
        self.page.show_dialog(dialog)
        self.page.update()

    def _show_add_connection_dialog(self, e: object = None) -> None:
        self.page.pop_dialog()
        self.page.update()
        protocol = self._connections_protocol
        protocol_field = ft.Dropdown(
            label="Protocol",
            value=protocol,
            options=[
                ft.DropdownOption(key="ssh", text="SSH"),
                ft.DropdownOption(key="ftp", text="FTP"),
            ],
            width=140,
        )
        host_field = ft.TextField(label="Host", hint_text="example.com")
        port_field = ft.TextField(label="Port", value="", hint_text="22")
        username_field = ft.TextField(label="Username")
        password_field = ft.TextField(
            label="Password", password=True, can_reveal_password=True
        )
        key_field = ft.TextField(
            label="SSH key path (optional)", hint_text="/home/user/.ssh/id_rsa"
        )
        project_name_field = ft.TextField(
            label="Project name",
            hint_text="Leave empty to use host",
            expand=True,
        )
        remote_dir_field = ft.TextField(
            label="Remote economy directory",
            hint_text="mpmissions/<map_name>",
            expand=True,
        )
        remote_profiles_field = ft.TextField(
            label="Remote profiles directory (optional)",
            hint_text="profiles",
            expand=True,
        )

        async def pick_key(ev: object) -> None:
            files = await ft.FilePicker().pick_files(
                dialog_title="Select SSH private key file"
            )
            if files:
                key_field.value = files[0].path
                key_field.update()

        key_browse_btn = ft.IconButton(
            icon=ft.Icons.FOLDER_OPEN,
            on_click=pick_key,
        )

        async def save(ev: object) -> None:
            cfg = self._build_connection_form(
                protocol_field,
                host_field,
                port_field,
                username_field,
                remote_dir_field,
                remote_profiles_field,
                key_field,
                project_name_field,
            )
            self._connection_manager.add(cfg, password_field.value or "")
            self.page.pop_dialog()
            self.page.update()
            self._show_connections_dialog()

        def cancel(ev: object) -> None:
            self.page.pop_dialog()
            self.page.update()
            self._show_connections_dialog()

        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("Add connection"),
            content=ft.Column(
                [
                    ft.Row([protocol_field, host_field], spacing=8),
                    ft.Row([port_field, username_field], spacing=8),
                    password_field,
                    ft.Row([key_field, key_browse_btn], spacing=4),
                    project_name_field,
                    remote_dir_field,
                    remote_profiles_field,
                ],
                scroll=ft.ScrollMode.AUTO,
                tight=True,
                width=520,
            ),
            actions=[
                ft.TextButton("Cancel", on_click=cancel),
                ft.TextButton("Save", on_click=save),
            ],
        )
        self.page.show_dialog(dialog)
        self.page.update()

    def _build_connection_form(
        self,
        protocol_field: object,
        host_field: object,
        port_field: object,
        username_field: object,
        remote_dir_field: object,
        remote_profiles_field: object,
        key_field: object,
        project_name_field: object,
    ) -> ConnectionConfig:
        return ConnectionConfig(
            id="",
            protocol=str(getattr(protocol_field, "value", "ssh")),
            host=str(getattr(host_field, "value", "")),
            port=int(str(getattr(port_field, "value")) or "0"),
            username=str(getattr(username_field, "value", "")),
            key_path=str(getattr(key_field, "value", "")),
            remote_economy_dir=str(getattr(remote_dir_field, "value", "")),
            remote_profiles_dir=str(getattr(remote_profiles_field, "value", "")),
            project_name=str(getattr(project_name_field, "value", "")),
        )

    async def _open_remote_project(self, cfg: ConnectionConfig) -> None:
        remote_dir = cfg.remote_economy_dir
        if not remote_dir:
            self._show_error("Set the remote economy directory first.")
            return
        local_staging = os.path.join(
            os.path.expanduser("~"), ".yetee", "workspace", cfg.id
        )
        local_profiles = os.path.join(
            os.path.expanduser("~"), ".yetee", "workspace", cfg.id, "profiles"
        )
        sync_progress = ft.ProgressBar(value=0, expand=True)
        sync_progress_text = ft.Text("… connecting", size=12)
        sync_dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("Opening remote project"),
            content=ft.Column(
                [
                    ft.Text(
                        f"Syncing files from {cfg.host}:{cfg.port}",
                        size=14,
                    ),
                    ft.Row([sync_progress]),
                    sync_progress_text,
                ],
                tight=True,
                width=420,
            ),
        )
        self.page.show_dialog(sync_dialog)
        self.page.update()
        started = time.monotonic()
        try:
            await self._remote_sync.sync_to_local(
                cfg,
                remote_dir,
                local_staging,
                remote_profiles_dir=cfg.remote_profiles_dir,
                local_profiles_dir=local_profiles if cfg.remote_profiles_dir else "",
                exclude_profiles=not_yet_available_entities(),
                on_progress=self._make_sync_progress(
                    sync_progress, sync_progress_text, started
                ),
            )
        except YeteeError as ex:
            self.page.pop_dialog()
            self._show_error(f"Failed to open remote project: {ex}")
            return
        except ValueError as ex:
            self.page.pop_dialog()
            self._show_error(str(ex))
            return
        except Exception as ex:  # noqa: BLE001
            self.page.pop_dialog()
            self._show_error(f"Failed to open remote project: {ex}")
            return
        self.page.pop_dialog()
        self._connection_manager.set_active(cfg.id)
        types_dir = EconomyService().get_types_dir(local_staging)
        project = Project(
            name=cfg.project_name or cfg.host,
            economy_dir=local_staging,
            types_dir=types_dir,
            profiles_dir=local_profiles if cfg.remote_profiles_dir else "",
            connection_id=cfg.id,
            remote_dir=remote_dir,
        )
        self._project_service.add_project(project)
        self.page.pop_dialog()
        self.page.update()
        self._open_project(project)

    def _make_sync_progress(
        self,
        progress: ft.ProgressBar,
        progress_text: ft.Text,
        started: float,
    ) -> Callable[[int, int], None]:
        def on_progress(done: int, total: int) -> None:
            fraction = done / total if total else 0
            progress.value = fraction
            progress.update()
            elapsed = time.monotonic() - started
            if done > 0 and elapsed > 0:
                rate = done / elapsed
                remaining = max(int((total - done) / rate), 0) if rate else 0
            else:
                remaining = 0
            progress_text.value = f"{done}/{total} · ~{remaining}s left"
            progress_text.update()

        return on_progress

    def _make_sync_status(self, progress_text: ft.Text) -> Callable[[str], None]:
        def on_status(message: str) -> None:
            progress_text.value = message
            progress_text.update()

        return on_status

    def _delete_connection(self, cfg: ConnectionConfig) -> None:
        self._connection_manager.remove(cfg.id)
        self.page.pop_dialog()
        self.page.update()
        self._show_connections_dialog()

    async def _test_connection(self, cfg: ConnectionConfig) -> None:
        print(
            f"[diag] _test_connection start: protocol={cfg.protocol} "
            f"host={cfg.host} port={cfg.port} user={cfg.username} "
            f"key={cfg.key_path!r} remote_dir={cfg.remote_economy_dir!r}"
        )
        try:
            conn = self._connection_manager.create(cfg)
            print(f"[diag] created connection object: {type(conn).__name__}")
            print("[diag] calling connect()...")
            await conn.connect()
            print("[diag] connect() returned OK")
            print("[diag] calling disconnect()...")
            await conn.disconnect()
            print("[diag] disconnect() returned OK")
        except YeteeError as ex:
            print(f"[diag] TEST FAILED (YeteeError): {type(ex).__name__}: {ex}")
            self._show_message("Connection failed", str(ex))
            return
        except Exception as ex:  # noqa: BLE001
            print(f"[diag] TEST FAILED (Exception): {type(ex).__name__}: {ex!r}")
            self._show_message("Connection failed", str(ex))
            return
        print("[diag] TEST SUCCESS")
        self._show_message(
            "Connection OK",
            f"Connected to {cfg.host}:{cfg.port} over {cfg.protocol.upper()}.",
        )

    def _show_message(self, title: str, message: str) -> None:
        dialog = ft.AlertDialog(
            title=ft.Text(title),
            content=ft.Text(message),
            actions=[
                ft.TextButton("OK", on_click=lambda _: self.page.pop_dialog()),
            ],
        )
        self.page.show_dialog(dialog)
        self.page.update()

    def _show_error(self, message: str) -> None:
        dialog = ft.AlertDialog(
            title=ft.Text("Error"),
            content=ft.Text(message),
            actions=[
                ft.TextButton("OK", on_click=lambda _: self.page.pop_dialog()),
            ],
        )
        self.page.show_dialog(dialog)
        self.page.update()

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

    async def _on_unhandled_editors_change(self, e: ft.ControlEvent) -> None:
        self.show_unhandled_mod_editors = bool(e.control.value)
        self._economy_editor.set_show_unhandled_editors(self.show_unhandled_mod_editors)
        await self._save_setting(
            "show_unhandled_mod_editors", self.show_unhandled_mod_editors
        )


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
        connection_manager=services["connection_manager"],
        remote_sync_service=services["remote_sync_service"],
        profile_service=services["profile_service"],
    )
    page.update()


if __name__ == "__main__":
    ft.run(main=main)
