from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import flet as ft
import pytest

from models.connection import ConnectionConfig
from services.entertainment_service import EntertainmentService
from ui.app_shell import AppShell
from ui.project_flow import ProjectFlow
from ui.remote_flow import RemoteFlow


def _cfg(**kw) -> ConnectionConfig:
    defaults = dict(
        id="c1",
        protocol="ssh",
        host="example.com",
        port=22,
        username="user",
        remote_economy_dir="mpmissions/chernarusplus",
    )
    defaults.update(kw)
    return ConnectionConfig(**defaults)


@pytest.fixture
def deps():
    page = MagicMock()
    task = MagicMock()
    task.done.return_value = False
    page.run_task.return_value = task
    connections = MagicMock()
    sync = MagicMock()
    sync.sync_to_local = AsyncMock()
    projects = MagicMock()
    profiles = MagicMock()
    profiles.scan_profiles.return_value = {}
    ent = EntertainmentService()
    editor = MagicMock()
    editor.settings_display = MagicMock()
    shell = AppShell(page, ent)
    pflow = ProjectFlow(page, projects, profiles, ent, editor, shell)
    flow = RemoteFlow(page, connections, sync, projects, pflow, editor)
    return page, connections, sync, projects, editor, pflow, flow


def test_on_local_saved_skips_local_project(deps):
    page, _, _, _, editor, _, flow = deps
    project = MagicMock()
    project.is_remote = False
    project.connection_id = None
    editor.project = project

    flow.on_local_saved()

    page.run_task.assert_not_called()


def test_on_local_saved_skips_missing_connection(deps):
    page, connections, _, _, editor, _, flow = deps
    project = MagicMock()
    project.is_remote = True
    project.connection_id = "c1"
    editor.project = project
    connections.get.return_value = None

    flow.on_local_saved()

    page.run_task.assert_not_called()


def test_on_local_saved_schedules_upload(deps):
    page, connections, _, _, editor, _, flow = deps
    project = MagicMock()
    project.is_remote = True
    project.connection_id = "c1"
    project.economy_dir = "/staging"
    project.remote_dir = "mpmissions/chernarusplus"
    project.profiles_dir = ""
    editor.project = project
    cfg = _cfg(remote_profiles_dir="")
    connections.get.return_value = cfg

    flow.on_local_saved()

    args = page.run_task.call_args.args
    assert args[0] == flow._upload_remote
    assert args[1] is cfg
    assert args[2] == "/staging"
    assert args[3] == "mpmissions/chernarusplus"


async def test_refresh_local_reloads_project(deps):
    page, _, _, _, editor, pflow, flow = deps
    pflow.preload_profile_files = MagicMock()
    project = MagicMock()

    await flow.refresh_local_project(project)

    editor.load_project.assert_called_once_with(project)
    pflow.preload_profile_files.assert_called_once_with(project, confirm=True)


async def test_refresh_remote_syncs_then_reloads(deps):
    page, connections, sync, _, editor, pflow, flow = deps
    pflow.preload_profile_files = MagicMock()
    cfg = _cfg()
    project = MagicMock()
    project.economy_dir = "/staging"
    project.remote_dir = "mpmissions/chernarusplus"
    project.profiles_dir = ""

    await flow.refresh_remote_project(cfg, project)

    sync.sync_to_local.assert_awaited_once()
    call = sync.sync_to_local.call_args
    assert call.args[1] == "mpmissions/chernarusplus"
    assert call.args[2] == "/staging"
    editor.load_project.assert_called_once_with(project)
    page.pop_dialog.assert_called()


async def test_refresh_remote_error_shows_dialog(deps):
    page, connections, sync, _, _, _, flow = deps
    sync.sync_to_local.side_effect = ValueError("bad path")
    cfg = _cfg()

    await flow.refresh_remote_project(cfg, MagicMock())

    error_dialog = page.show_dialog.call_args.args[0]
    assert error_dialog.title.value == "Error"
    assert "bad path" in error_dialog.content.value


async def test_open_remote_shows_sync_dialog(deps):
    page, connections, sync, projects, _, _, flow = deps
    cfg = _cfg()

    await flow.open_remote_project(cfg)

    page.show_dialog.assert_called_once()
    dialog = page.show_dialog.call_args_list[0].args[0]
    assert dialog.title.value == "Opening remote project"
    rows = [c for c in dialog.content.controls if isinstance(c, ft.Row)]
    assert any(
        any(isinstance(sub, ft.ProgressBar) for sub in row.controls) for row in rows
    )
    sync.sync_to_local.assert_awaited_once()
    assert sync.sync_to_local.call_args.kwargs.get("on_progress") is not None
    connections.set_active.assert_called_once_with("c1")
    projects.add_project.assert_called_once()


async def test_open_remote_closes_dialog_on_error(deps):
    page, connections, sync, _, _, _, flow = deps
    sync.sync_to_local.side_effect = ConnectionError("boom")
    cfg = _cfg()

    await flow.open_remote_project(cfg)

    sync_dialog = page.show_dialog.call_args_list[0].args[0]
    assert sync_dialog.title.value == "Opening remote project"
    assert page.pop_dialog.called
    error_dialog = page.show_dialog.call_args_list[1].args[0]
    assert error_dialog.title.value == "Error"
    assert "boom" in error_dialog.content.value


async def test_open_remote_requires_remote_dir(deps):
    page, _, sync, _, _, _, flow = deps
    cfg = _cfg(remote_economy_dir="")

    await flow.open_remote_project(cfg)

    sync.sync_to_local.assert_not_awaited()
    error_dialog = page.show_dialog.call_args.args[0]
    assert error_dialog.title.value == "Error"


def test_connections_dialog_lists_by_protocol(deps):
    page, connections, _, _, _, _, flow = deps
    ssh = _cfg(project_name="Prod")
    ftp = ConnectionConfig(
        id="c2",
        protocol="ftp",
        host="ftp.example.com",
        port=21,
        username="u",
    )
    connections.list_connections.return_value = [ssh, ftp]

    flow.show_connections_dialog(protocol="ssh")

    dialog = page.show_dialog.call_args.args[0]
    assert dialog.title.value == "SSH Connections"
    texts: list[str] = []

    def collect(ctrl):
        if isinstance(ctrl, ft.Text):
            texts.append(ctrl.value)
        for child in getattr(ctrl, "controls", []) or []:
            collect(child)

    collect(dialog.content)
    assert any("Prod" in v for v in texts)


def test_delete_connection_removes_and_refreshes(deps):
    page, connections, _, _, _, _, flow = deps
    connections.list_connections.return_value = []

    flow.delete_connection(_cfg())

    connections.remove.assert_called_once_with("c1")
    page.pop_dialog.assert_called()
