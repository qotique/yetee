from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import Callable

import flet as ft

from models.project import Project
from services.economy_service import EconomyService
from services.entertainment_service import EntertainmentService
from services.profile_service import ProfileService
from services.profile_preload_service import estimate_preload, should_confirm
from services.project_service import ProjectService
from ui.app_shell import AppShell
from ui.economy_editor import EconomyEditor
from ui.settings_table_display import SettingsTableDisplay
from ui.dialogs import show_error

logger = logging.getLogger(__name__)


class ProjectFlow:
    def __init__(
        self,
        page: ft.Page,
        project_service: ProjectService,
        profile_service: ProfileService,
        entertainment_service: EntertainmentService,
        economy_editor: EconomyEditor,
        shell: AppShell,
    ) -> None:
        self.page = page
        self._projects = project_service
        self._profiles = profile_service
        self._entertainment = entertainment_service
        self._editor = economy_editor
        self._shell = shell

    def restore_last_project(self) -> None:
        last = self._projects.get_last_project()
        if last is not None and os.path.isdir(last.economy_dir):
            self.open_project(last)

    def refresh_project_dropdown(self) -> None:
        projects = self._projects.load_projects()
        selected: str | None = None
        if self._editor.project is not None:
            selected = self._editor.project.name
        elif projects:
            selected = projects[-1].name
        self._shell.refresh_project_options(
            [p.name for p in projects], selected
        )

    def open_project(self, project: Project) -> None:
        self._projects.mark_opened(project)
        self._shell.set_project_ui_open(True)
        self._editor.load_project(project)
        self.refresh_project_dropdown()
        self.refresh_entity_selectors()
        self._shell.update_cat_icons()
        self.page.update()
        self.preload_profile_files(project, confirm=False)

    def reload_project(self, project: Project) -> None:
        self._editor.load_project(project)
        self.refresh_entity_selectors()
        self.page.update()
        self.preload_profile_files(project, confirm=True)

    def preload_profile_files(self, project: Project, *, confirm: bool) -> None:
        if not project.profiles_dir:
            return
        settings_display = self._editor.settings_display
        if settings_display is None:
            return
        scanned = self._profiles.scan_profiles(project.profiles_dir)
        files = sorted(
            path
            for entity, paths in scanned.items()
            if self._editor.is_editable_entity(entity)
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
        settings_display = self._editor.settings_display
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

    def show_new_project_dialog(
        self,
        e: object = None,
        name: str = "",
        economy_dir: str = "",
        profiles_dir: str = "",
        remote_opener: Callable[[str], None] | None = None,
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
            new_name = name_field.value
            new_dir = economy_dir_field.value
            if not new_name or not new_dir:
                return
            if not os.path.isdir(new_dir):
                logger.warning("Economy directory does not exist: %s", new_dir)
                return
            self.page.pop_dialog()
            self.page.update()
            self.create_project(
                new_name,
                new_dir,
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

        remote_buttons: list[ft.Control] = []
        if remote_opener is not None:
            opener = remote_opener

            def open_ssh(ev: object) -> None:
                opener("ssh")

            def open_ftp(ev: object) -> None:
                opener("ftp")

            remote_buttons = [
                ft.TextButton("via SSH...", on_click=open_ssh),
                ft.TextButton("via FTP...", on_click=open_ftp),
            ]

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
                            *remote_buttons,
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

    def create_project(
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
            self._projects.add_project(project)
            self.open_project(project)
        except Exception as ex:  # noqa: BLE001
            logger.error("Failed to create project: %s", ex)
            show_error(self.page, f"Failed to create project: {ex}")

    def show_open_project_dialog(self, e: object = None) -> None:
        projects = self._projects.load_projects()
        if not projects:
            dialog = ft.AlertDialog(
                title=ft.Text("No Projects"),
                content=ft.Text(
                    "No saved projects found. Create a new project first."
                ),
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
            project = self._projects.get_project(name)
            if project is None:
                return
            self.page.pop_dialog()
            self.page.update()
            self.open_project(project)

        def do_delete(ev: object) -> None:
            name = dropdown.value
            if not name:
                return
            self._projects.remove_project(name)
            self.refresh_project_dropdown()
            self.page.pop_dialog()
            self.show_open_project_dialog()

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

    def on_project_switch(self, e: object) -> None:
        name = self._shell.project_dropdown.value
        if not name:
            return
        project = self._projects.get_project(name)
        if project is not None:
            self._editor.save_file()
            self.open_project(project)

    def delete_project_flow(self, e: object = None) -> None:
        project = self._editor.project
        if project is None:
            return

        def confirm(ev: object) -> None:
            self.page.pop_dialog()
            self._projects.remove_project(project.name)
            self._editor.unload()
            self._shell.set_project_ui_open(False)
            self.refresh_project_dropdown()
            self.refresh_entity_selectors()
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

    def refresh_entity_selectors(self) -> None:
        entities = self._editor.available_entities
        self._shell.refresh_entity_options(entities, self._editor.current_entity)

    def on_entity_switch(self, e: object) -> None:
        entity = self._shell.entity_dropdown.value
        if entity:
            self._editor.switch_entity(entity)
            self.refresh_entity_selectors()

    async def select_economy_dir(self, e: object = None) -> None:
        path = await ft.FilePicker().get_directory_path(
            dialog_title="Select economy directory (mpmissions/<map_name>)",
        )
        if not path:
            return
        name = os.path.basename(path)
        if not name:
            name = "MyProject"
        self.create_project(name, path)
