from __future__ import annotations

from unittest.mock import MagicMock

from services.entertainment_service import EntertainmentService
from ui.app_shell import AppShell


def _shell():
    page = MagicMock()
    ent = EntertainmentService()
    return AppShell(page, ent), page


def test_builds_all_widgets():
    shell, _ = _shell()
    assert shell.title_bar is not None
    assert shell.content_stack is not None
    assert shell.start_container.visible is True
    assert shell.save_btn.visible is False
    assert shell.settings_overlay.visible is False
    for btn in (
        shell.start_new_project_btn,
        shell.start_ssh_btn,
        shell.start_ftp_btn,
        shell.start_open_project_btn,
        shell.start_select_dir_btn,
    ):
        assert btn is not None


def test_attach_editor_appends_control():
    shell, _ = _shell()
    editor = MagicMock()
    shell.attach_editor(editor.control)
    assert editor.control in shell.content_column.controls


def test_set_project_ui_open_toggles_visibility():
    shell, _ = _shell()
    editor = MagicMock()
    shell.attach_editor(editor.control)

    shell.set_project_ui_open(True)
    assert editor.control.visible is True
    assert shell.start_container.visible is False
    assert shell.save_btn.visible is True

    shell.set_project_ui_open(False)
    assert editor.control.visible is False
    assert shell.start_container.visible is True
    assert shell.save_btn.visible is False


def test_settings_overlay_open_close():
    shell, _ = _shell()
    shell.open_settings()
    assert shell.settings_overlay.visible is True
    shell.close_settings()
    assert shell.settings_overlay.visible is False


def test_sync_settings_controls_reads_manager_and_entertainment():
    from controllers.settings_manager import SettingsManager

    shell, _ = _shell()
    manager = SettingsManager(MagicMock(), MagicMock())
    manager.selected_theme = "DARK"
    manager.check_updates = False
    manager.show_unhandled_mod_editors = True

    shell.sync_settings_controls(manager)

    assert shell.theme_dropdown.value == "DARK"
    assert shell.check_updates_switch.value is False
    assert shell.unhandled_editors_switch.value is True


def test_cat_icons_switch():
    import flet as ft

    shell, page = _shell()
    shell.update_cat_icons()
    assert shell.new_project_btn.icon == ft.Icons.ADD_BOX
    assert shell.settings_btn.icon == ft.Icons.SETTINGS

    shell._entertainment.cat_mode = True
    shell.update_cat_icons()
    assert shell.new_project_btn.icon == ft.Icons.PETS
    assert shell.delete_project_btn.icon == ft.Icons.PETS
