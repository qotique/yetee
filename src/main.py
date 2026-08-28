from __future__ import annotations

import logging

import flet as ft

import models.expansion  # noqa: F401  (registers Expansion schemas at import)
from controllers.settings_manager import SettingsManager
from core.di import create_app_services
from core.exceptions import YeteeError
from core.logging_setup import setup_logging
from services.connection_manager import ConnectionManager
from services.entertainment_service import EntertainmentService
from services.profile_service import ProfileService
from services.remote_sync_service import RemoteSyncService
from services.config_service import ConfigService
from services.settings_service import THEMES, SettingsService
from services.project_service import ProjectService
from services.update_service import UpdateService
from models.connection import ConnectionConfig
from models.project import Project
from ui.app_shell import AppShell
from ui.dialogs import show_message
from ui.economy_editor import EconomyEditor
from ui.project_flow import ProjectFlow
from ui.remote_flow import RemoteFlow

logger = logging.getLogger(__name__)

VERSION = "0.6.2"


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

        self.settings_manager = SettingsManager(
            settings_service, entertainment_service
        )
        self.shell = AppShell(page, entertainment_service)
        self.shell.attach_editor(economy_editor.control)
        self.project_flow = ProjectFlow(
            page,
            project_service,
            self._profile_service,
            entertainment_service,
            economy_editor,
            self.shell,
        )
        self.remote_flow = RemoteFlow(
            page,
            self._connection_manager,
            self._remote_sync,
            project_service,
            self.project_flow,
            economy_editor,
        )
        self._wire_actions()

        page.title = "Yet Another Types Editing Environment | YETEE"
        page.window.title_bar_hidden = True
        page.window.maximized = True
        page.theme_mode = THEMES[self.settings_manager.selected_theme]
        page.on_route_change = self.route_change
        page.on_view_pop = self.view_pop

        self.shell.ensure_main_view()
        self.page.update()
        self.page.run_task(self._load_settings)

    def _wire_actions(self) -> None:
        editor = self._economy_editor
        editor.file_display.on_saved = self.remote_flow.on_local_saved
        editor.event_display.on_saved = self.remote_flow.on_local_saved
        if editor.settings_display is not None:
            editor.settings_display.on_saved = self.remote_flow.on_local_saved
        if editor.form_display is not None:
            editor.form_display.on_saved = self.remote_flow.on_local_saved

        shell = self.shell
        projects = self.project_flow
        remote = self.remote_flow

        shell.project_dropdown.on_select = projects.on_project_switch
        shell.entity_dropdown.on_select = projects.on_entity_switch
        shell.new_project_btn.on_click = projects.show_new_project_dialog
        shell.delete_project_btn.on_click = projects.delete_project_flow
        shell.refresh_btn.on_click = remote.on_refresh_project
        shell.save_btn.on_click = self._on_save
        shell.settings_btn.on_click = shell.open_settings
        shell.connections_btn.on_click = remote.show_connections_dialog

        shell.start_new_project_btn.on_click = projects.show_new_project_dialog
        shell.start_ssh_btn.on_click = lambda e: remote.show_connections_dialog(
            protocol="ssh"
        )
        shell.start_ftp_btn.on_click = lambda e: remote.show_connections_dialog(
            protocol="ftp"
        )
        shell.start_open_project_btn.on_click = projects.show_open_project_dialog
        shell.start_select_dir_btn.on_click = projects.select_economy_dir

        shell.theme_dropdown.on_select = self._on_theme_change
        shell.language_dropdown.on_select = self._on_language_change
        shell.check_updates_switch.on_change = self._on_check_updates_change
        shell.unhandled_editors_switch.on_change = self._on_unhandled_editors_change
        shell.fun_messages_switch.on_change = self._on_fun_messages_change
        shell.meme_switch.on_change = self._on_meme_change
        shell.cat_mode_switch.on_change = self._on_cat_mode_change
        shell.terminal_mode_switch.on_change = self._on_terminal_mode_change
        shell.funny_enabled_switch.on_change = self._on_funny_enabled_change

    def build_main_view(self) -> ft.View:
        return self.shell.build_main_view()

    def route_change(self, route: object = None) -> None:
        self.shell.ensure_main_view()

    async def view_pop(self, e: ft.ViewPopEvent) -> None:
        if self.shell.settings_overlay.visible:
            self.shell.close_settings()

    async def _load_settings(self) -> None:
        try:
            settings = await self._settings_service.load_settings()
            self.settings_manager.apply_startup(settings)
            self.page.theme_mode = THEMES[self.settings_manager.selected_theme]
            self.shell.sync_settings_controls(self.settings_manager)
            self._economy_editor.set_show_unhandled_editors(
                self.settings_manager.show_unhandled_mod_editors
            )
            self.shell.update_cat_icons()
            self.page.update()
            if self.settings_manager.check_updates:
                await self._update_service.check_for_updates(VERSION)
        except YeteeError:
            logger.warning("Failed to load settings", exc_info=True)
        except Exception as ex:  # noqa: BLE001
            logger.error("Unexpected error loading settings: %s", ex)

        self.project_flow.restore_last_project()
        self.page.update()

    @property
    def show_unhandled_mod_editors(self) -> bool:
        return self.settings_manager.show_unhandled_mod_editors

    def _preload_profile_files(self, project: Project, *, confirm: bool) -> None:
        self.project_flow.preload_profile_files(project, confirm=confirm)

    async def _refresh_local_project(self, project: Project) -> None:
        await self.remote_flow.refresh_local_project(project)

    async def _refresh_remote_project(
        self, cfg: ConnectionConfig, project: Project
    ) -> None:
        await self.remote_flow.refresh_remote_project(cfg, project)

    async def _open_remote_project(self, cfg: ConnectionConfig) -> None:
        await self.remote_flow.open_remote_project(cfg)

    def _show_new_project_dialog(
        self,
        e: object = None,
        name: str = "",
        economy_dir: str = "",
        profiles_dir: str = "",
    ) -> None:
        self.project_flow.show_new_project_dialog(
            e,
            name=name,
            economy_dir=economy_dir,
            profiles_dir=profiles_dir,
            remote_opener=self.remote_flow.show_connections_dialog,
        )

    def _on_save(self, e: object) -> None:
        self._economy_editor.save_current(e)
        self.remote_flow.on_local_saved()

    async def _on_theme_change(self, e: ft.ControlEvent) -> None:
        theme = e.control.value
        if await self.settings_manager.set_theme(theme):
            self.page.theme_mode = THEMES[theme]
            self.page.update()

    async def _on_language_change(self, e: ft.ControlEvent) -> None:
        lang = e.control.value
        if not await self.settings_manager.set_language(lang):
            return
        if lang != "English":
            show_message(self.page, "Not available", "Language support coming soon.")
        self.page.update()

    async def _on_check_updates_change(self, e: ft.ControlEvent) -> None:
        await self.settings_manager.set_check_updates(bool(e.control.value))

    async def _on_fun_messages_change(self, e: ft.ControlEvent) -> None:
        await self.settings_manager.set_fun_flag(
            "fun_save_messages", bool(e.control.value)
        )

    async def _on_meme_change(self, e: ft.ControlEvent) -> None:
        await self.settings_manager.set_fun_flag(
            "show_meme_on_save", bool(e.control.value)
        )

    async def _on_cat_mode_change(self, e: ft.ControlEvent) -> None:
        await self.settings_manager.set_fun_flag("cat_mode", bool(e.control.value))
        self._economy_editor.file_display.update_cat_icons()
        self._economy_editor.event_display.update_cat_icons()
        self.shell.update_cat_icons()
        self.page.update()

    async def _on_terminal_mode_change(self, e: ft.ControlEvent) -> None:
        await self.settings_manager.set_fun_flag(
            "terminal_mode", bool(e.control.value)
        )

    async def _on_funny_enabled_change(self, e: ft.ControlEvent) -> None:
        await self.settings_manager.set_fun_flag(
            "funny_enabled", bool(e.control.value)
        )
        self._economy_editor.file_display.update_funny_visibility()

    async def _on_unhandled_editors_change(self, e: ft.ControlEvent) -> None:
        value = bool(e.control.value)
        await self.settings_manager.set_unhandled_editors(value)
        self._economy_editor.set_show_unhandled_editors(value)


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
