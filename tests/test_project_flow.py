from __future__ import annotations

from unittest.mock import MagicMock

import flet as ft
import pytest

from services.entertainment_service import EntertainmentService
from services.profile_preload_service import PROFILE_PRELOAD_DIALOG_MIN_FILES
from ui.app_shell import AppShell
from ui.project_flow import ProjectFlow


@pytest.fixture
def deps():
    page = MagicMock()
    task = MagicMock()
    task.done.return_value = False
    page.run_task.return_value = task
    projects = MagicMock()
    profiles = MagicMock()
    ent = EntertainmentService()
    editor = MagicMock()
    editor.settings_display = MagicMock()
    shell = AppShell(page, ent)
    flow = ProjectFlow(page, projects, profiles, ent, editor, shell)
    return page, projects, profiles, editor, shell, flow


def _write_profiles(root, count):
    files_map = {}
    for i in range(count):
        d = root / f"Mod{i}"
        d.mkdir(parents=True, exist_ok=True)
        f = d / f"{i}.json"
        f.write_text("{}")
        files_map[f"Mod{i}"] = {f"{i}.json": str(f)}
    return files_map


def test_preload_few_files_runs_directly(deps, tmp_path):
    page, projects, profiles, editor, _, flow = deps
    profiles.scan_profiles.return_value = _write_profiles(tmp_path / "p", 3)
    project = MagicMock()
    project.profiles_dir = str(tmp_path / "p")

    flow.preload_profile_files(project, confirm=True)

    args = page.run_task.call_args.args
    assert args and args[0] is editor.settings_display.preload_cached
    page.show_dialog.assert_not_called()


def test_preload_skips_not_yet_available(deps, tmp_path):
    page, projects, profiles, editor, _, flow = deps
    root = tmp_path / "p"
    (root / "TraderX").mkdir(parents=True)
    (root / "TraderX" / "traderconfig.json").write_text("{}")
    (root / "CustomMod").mkdir()
    (root / "CustomMod" / "cfg.json").write_text("{}")
    profiles.scan_profiles.return_value = {
        "TraderX": {
            "traderconfig.json": str(root / "TraderX" / "traderconfig.json")
        },
        "CustomMod": {"cfg.json": str(root / "CustomMod" / "cfg.json")},
    }
    editor.is_editable_entity.side_effect = lambda e: e == "CustomMod"
    project = MagicMock()
    project.profiles_dir = str(root)

    flow.preload_profile_files(project, confirm=True)

    args = page.run_task.call_args.args
    assert args[1] == [str(root / "CustomMod" / "cfg.json")]


def test_preload_many_files_shows_dialog(deps, tmp_path):
    page, projects, profiles, editor, _, flow = deps
    root = tmp_path / "p"
    n = PROFILE_PRELOAD_DIALOG_MIN_FILES + 1
    profiles.scan_profiles.return_value = _write_profiles(root, n)
    project = MagicMock()
    project.profiles_dir = str(root)

    flow.preload_profile_files(project, confirm=True)

    editor.settings_display.preload_cached.assert_not_called()
    page.show_dialog.assert_called_once()
    dialog = page.show_dialog.call_args.args[0]
    assert dialog.title.value == "Loading profiles"
    assert any(isinstance(c, ft.Row) for c in dialog.content.controls)


def test_preload_confirm_false_skips_dialog(deps, tmp_path):
    page, projects, profiles, editor, _, flow = deps
    root = tmp_path / "p"
    n = PROFILE_PRELOAD_DIALOG_MIN_FILES + 1
    profiles.scan_profiles.return_value = _write_profiles(root, n)
    project = MagicMock()
    project.profiles_dir = str(root)

    flow.preload_profile_files(project, confirm=False)

    args = page.run_task.call_args.args
    assert args and args[0] is editor.settings_display.preload_cached
    page.show_dialog.assert_not_called()


def test_reload_project_loads_and_preloads(deps, tmp_path):
    page, projects, profiles, editor, _, flow = deps
    root = tmp_path / "p"
    profiles.scan_profiles.return_value = _write_profiles(root, 1)
    project = MagicMock()
    project.profiles_dir = str(root)
    project.is_remote = False

    flow.reload_project(project)

    editor.load_project.assert_called_once_with(project)
    args = page.run_task.call_args.args
    assert args and args[0] is editor.settings_display.preload_cached


def test_open_project_toggles_ui_and_refreshes(deps):
    page, projects, profiles, editor, shell, flow = deps
    project = MagicMock()
    project.profiles_dir = ""
    projects.load_projects.return_value = [project]

    flow.open_project(project)

    projects.mark_opened.assert_called_once_with(project)
    editor.load_project.assert_called_once_with(project)
    assert shell.save_btn.visible is True
    assert shell.start_container.visible is False
    page.update.assert_called()


def test_delete_flow_unloads_and_hides_ui(deps):
    page, projects, profiles, editor, shell, flow = deps
    project = MagicMock()
    project.name = "P"
    editor.project = project

    flow.delete_project_flow()

    page.show_dialog.assert_called_once()
    dialog = page.show_dialog.call_args.args[0]
    confirm_btn = dialog.actions[1]
    confirm_btn.on_click(None)
    projects.remove_project.assert_called_once_with("P")
    editor.unload.assert_called_once()
    assert shell.start_container.visible is True
    assert shell.save_btn.visible is False


def test_restore_last_project_opens_existing_dir(deps):
    _, projects, _, editor, _, flow = deps
    project = MagicMock()
    project.economy_dir = "/existing"
    projects.get_last_project.return_value = project

    import os

    with __import__("unittest").mock.patch.object(os.path, "isdir", return_value=True):
        flow.restore_last_project()

    editor.load_project.assert_called_once_with(project)


def test_restore_last_project_skips_missing_dir(deps):
    _, projects, _, editor, _, flow = deps
    project = MagicMock()
    project.economy_dir = "/missing"
    projects.get_last_project.return_value = project

    flow.restore_last_project()

    editor.load_project.assert_not_called()


def test_create_project_failure_shows_error(deps):
    page, projects, _, editor, _, flow = deps
    projects.add_project.side_effect = RuntimeError("disk full")

    flow.create_project("X", "/some/dir")

    page.show_dialog.assert_called_once()
    dialog = page.show_dialog.call_args.args[0]
    assert dialog.title.value == "Error"
