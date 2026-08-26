from __future__ import annotations

import logging
import os
import time
from collections.abc import Callable

import flet as ft

from core.exceptions import YeteeError
from models.connection import ConnectionConfig
from models.mod_handlers import not_yet_available_entities
from models.project import Project
from services.connection_manager import ConnectionManager
from services.economy_service import EconomyService
from services.project_service import ProjectService
from services.remote_sync_service import RemoteSyncService
from ui.dialogs import show_error, show_message
from ui.economy_editor import EconomyEditor
from ui.project_flow import ProjectFlow

logger = logging.getLogger(__name__)


class RemoteFlow:
    def __init__(
        self,
        page: ft.Page,
        connection_manager: ConnectionManager,
        remote_sync_service: RemoteSyncService,
        project_service: ProjectService,
        project_flow: ProjectFlow,
        economy_editor: EconomyEditor,
    ) -> None:
        self.page = page
        self._connections = connection_manager
        self._sync = remote_sync_service
        self._projects = project_service
        self._project_flow = project_flow
        self._editor = economy_editor
        self._protocol: str = "ssh"

    def show_connections_dialog(
        self, e: object = None, protocol: str | None = None
    ) -> None:
        if protocol is not None:
            self._protocol = protocol
        connections = [
            c
            for c in self._connections.list_connections()
            if c.protocol == self._protocol
        ]
        if not connections:
            hint: ft.Text | None = ft.Text(
                f"No {self._protocol.upper()} connections yet. "
                f"Click Add to connect to a server over {self._protocol.upper()}.",
                color=ft.Colors.GREY_500,
            )
        else:
            hint = None

        rows: list[ft.Control] = []
        for index, cfg in enumerate(connections):
            label = cfg.project_name or cfg.host
            title = f"{label} · {cfg.host}:{cfg.port} ({cfg.username})"
            subtitle = (
                f"Remote dir: {cfg.remote_economy_dir or 'not set'} | "
                f"Profiles: {cfg.remote_profiles_dir or 'not set'}"
            )

            async def open_remote(_e: object, c: ConnectionConfig = cfg) -> None:
                await self.open_remote_project(c)

            async def test_conn(_e: object, c: ConnectionConfig = cfg) -> None:
                logger.debug("Test button clicked for %s %s:%s", c.protocol, c.host, c.port)
                await self.test_connection(c)

            del_btn = ft.TextButton(
                "Delete",
                on_click=lambda _e, c=cfg: self.delete_connection(c),
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
            title=ft.Text(f"{self._protocol.upper()} Connections"),
            content=ft.Column(
                [hint] + rows if hint else rows,
                scroll=ft.ScrollMode.AUTO,
                width=560,
            ),
            actions=[
                ft.TextButton("Add", on_click=self.show_add_connection_dialog),
                ft.TextButton("Close", on_click=lambda _: self.page.pop_dialog()),
            ],
        )
        self.page.show_dialog(dialog)
        self.page.update()

    def show_add_connection_dialog(self, e: object = None) -> None:
        self.page.pop_dialog()
        self.page.update()
        protocol_field = ft.Dropdown(
            label="Protocol",
            value=self._protocol,
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

        key_browse_btn = ft.IconButton(icon=ft.Icons.FOLDER_OPEN, on_click=pick_key)

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
            self._connections.add(cfg, password_field.value or "")
            self.page.pop_dialog()
            self.page.update()
            self.show_connections_dialog()

        def cancel(ev: object) -> None:
            self.page.pop_dialog()
            self.page.update()
            self.show_connections_dialog()

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

    def delete_connection(self, cfg: ConnectionConfig) -> None:
        self._connections.remove(cfg.id)
        self.page.pop_dialog()
        self.page.update()
        self.show_connections_dialog()

    async def test_connection(self, cfg: ConnectionConfig) -> None:
        logger.debug(
            "Testing connection: protocol=%s host=%s port=%s user=%s key=%r "
            "remote_dir=%r",
            cfg.protocol,
            cfg.host,
            cfg.port,
            cfg.username,
            cfg.key_path,
            cfg.remote_economy_dir,
        )
        try:
            conn = self._connections.create(cfg)
            logger.debug("Created connection object: %s", type(conn).__name__)
            await conn.connect()
            await conn.disconnect()
        except YeteeError as ex:
            logger.debug("TEST FAILED (YeteeError): %s: %s", type(ex).__name__, ex)
            show_message(self.page, "Connection failed", str(ex))
            return
        except Exception as ex:  # noqa: BLE001
            logger.debug("TEST FAILED (Exception): %s: %r", type(ex).__name__, ex)
            show_message(self.page, "Connection failed", str(ex))
            return
        logger.debug("TEST SUCCESS")
        show_message(
            self.page,
            "Connection OK",
            f"Connected to {cfg.host}:{cfg.port} over {cfg.protocol.upper()}.",
        )

    async def open_remote_project(self, cfg: ConnectionConfig) -> None:
        remote_dir = cfg.remote_economy_dir
        if not remote_dir:
            show_error(self.page, "Set the remote economy directory first.")
            return
        local_staging = os.path.join(
            os.path.expanduser("~"), ".yetee", "workspace", cfg.id
        )
        local_profiles = os.path.join(
            os.path.expanduser("~"), ".yetee", "workspace", cfg.id, "profiles"
        )
        dialog, progress, progress_text = self._build_sync_dialog(
            "Opening remote project", cfg
        )
        self.page.show_dialog(dialog)
        self.page.update()
        started = time.monotonic()
        try:
            await self._sync.sync_to_local(
                cfg,
                remote_dir,
                local_staging,
                remote_profiles_dir=cfg.remote_profiles_dir,
                local_profiles_dir=local_profiles if cfg.remote_profiles_dir else "",
                exclude_profiles=not_yet_available_entities(),
                on_progress=self._make_sync_progress(progress, progress_text, started),
            )
        except YeteeError as ex:
            self._close_sync_and_error(f"Failed to open remote project: {ex}")
            return
        except ValueError as ex:
            self._close_sync_and_error(str(ex))
            return
        except Exception as ex:  # noqa: BLE001
            self._close_sync_and_error(f"Failed to open remote project: {ex}")
            return
        self.page.pop_dialog()
        self._connections.set_active(cfg.id)
        types_dir = EconomyService().get_types_dir(local_staging)
        project = Project(
            name=cfg.project_name or cfg.host,
            economy_dir=local_staging,
            types_dir=types_dir,
            profiles_dir=local_profiles if cfg.remote_profiles_dir else "",
            connection_id=cfg.id,
            remote_dir=remote_dir,
        )
        self._projects.add_project(project)
        self.page.pop_dialog()
        self.page.update()
        self._project_flow.open_project(project)

    def _close_sync_and_error(self, message: str) -> None:
        self.page.pop_dialog()
        show_error(self.page, message)

    def _build_sync_dialog(
        self, title: str, cfg: ConnectionConfig
    ) -> tuple[ft.AlertDialog, ft.ProgressBar, ft.Text]:
        progress = ft.ProgressBar(value=0, expand=True)
        progress_text = ft.Text("… connecting", size=12)
        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text(title),
            content=ft.Column(
                [
                    ft.Text(f"Syncing files from {cfg.host}:{cfg.port}", size=14),
                    ft.Row([progress]),
                    progress_text,
                ],
                tight=True,
                width=420,
            ),
        )
        return dialog, progress, progress_text

    def on_local_saved(self) -> None:
        project = self._editor.project
        if project is None or not project.is_remote or not project.connection_id:
            return
        cfg = self._connections.get(project.connection_id)
        if cfg is None:
            logger.debug("No connection config found, skip upload")
            return
        logger.debug(
            "Local saved; scheduling upload to %s",
            project.remote_dir or cfg.remote_economy_dir,
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
            logger.debug("run_task error: %r", ex)

    async def _upload_remote(
        self,
        cfg: ConnectionConfig,
        local_dir: str,
        remote_dir: str,
        local_profiles_dir: str = "",
        remote_profiles_dir: str = "",
    ) -> None:
        logger.debug("Upload start: %s -> %s", local_dir, remote_dir)
        try:
            await self._sync.upload_to_remote(
                cfg,
                local_dir,
                remote_dir,
                local_profiles_dir=local_profiles_dir,
                remote_profiles_dir=remote_profiles_dir,
                exclude_profiles=not_yet_available_entities(),
            )
            logger.debug("UPLOAD OK")
        except Exception as ex:  # noqa: BLE001
            logger.debug("UPLOAD FAILED: %s: %r", type(ex).__name__, ex)

    def on_refresh_project(self, e: object = None) -> None:
        project = self._editor.project
        if project is None:
            return
        if project.is_remote and project.connection_id:
            cfg = self._connections.get(project.connection_id)
            if cfg is None:
                show_error(self.page, "Connection not found for refresh.")
                return
            self.page.run_task(self.refresh_remote_project, cfg, project)
        else:
            self.page.run_task(self.refresh_local_project, project)

    async def refresh_local_project(self, project: Project) -> None:
        self._project_flow.reload_project(project)

    async def refresh_remote_project(
        self, cfg: ConnectionConfig, project: Project
    ) -> None:
        remote_dir = project.remote_dir or cfg.remote_economy_dir
        if not remote_dir:
            show_error(self.page, "Set the remote economy directory first.")
            return
        local_profiles = (
            project.profiles_dir if cfg.remote_profiles_dir else ""
        )
        dialog, progress, progress_text = self._build_sync_dialog(
            "Refreshing project", cfg
        )
        self.page.show_dialog(dialog)
        self.page.update()
        started = time.monotonic()
        try:
            await self._sync.sync_to_local(
                cfg,
                remote_dir,
                project.economy_dir,
                remote_profiles_dir=cfg.remote_profiles_dir,
                local_profiles_dir=local_profiles if local_profiles else "",
                exclude_profiles=not_yet_available_entities(),
                on_progress=self._make_sync_progress(progress, progress_text, started),
            )
        except YeteeError as ex:
            self._close_sync_and_error(f"Failed to refresh project: {ex}")
            return
        except ValueError as ex:
            self._close_sync_and_error(str(ex))
            return
        except Exception as ex:  # noqa: BLE001
            self._close_sync_and_error(f"Failed to refresh project: {ex}")
            return
        self.page.pop_dialog()
        self._project_flow.reload_project(project)

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
