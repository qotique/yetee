"""Tests for the FunPresenter entertainment UI helper."""

from __future__ import annotations

import asyncio
import json
import urllib.request
from unittest.mock import MagicMock, patch

import flet as ft

from models.row_data import RowData
from services.entertainment_service import (
    EntertainmentService,
    FUN_SAVE_MESSAGES,
)
from ui.fun_presenter import FunPresenter


def _make_presenter(page, ent=None):
    return FunPresenter(
        page,
        ent,
        tips_switcher=MagicMock(),
        save_text=MagicMock(),
    )


def test_icon_for_returns_pets_in_cat_mode(mock_page):
    ent = EntertainmentService()
    ent.cat_mode = True
    presenter = _make_presenter(mock_page, ent)
    assert presenter.icon_for(ft.Icons.ADD) == ft.Icons.PETS


def test_icon_for_returns_normal_without_cat(mock_page):
    presenter = _make_presenter(mock_page, None)
    assert presenter.icon_for(ft.Icons.ADD) == ft.Icons.ADD


def test_fab_icon_switches_on_shift(mock_page):
    presenter = _make_presenter(mock_page, None)
    assert presenter.fab_icon(False) == ft.Icons.ADD
    assert presenter.fab_icon(True) == ft.Icons.DELETE


def test_is_cat_reflects_service_flag(mock_page):
    ent = EntertainmentService()
    assert _make_presenter(mock_page, ent).is_cat() is False
    ent.cat_mode = True
    assert _make_presenter(mock_page, ent).is_cat() is True


def test_update_funny_visibility_toggles_buttons(mock_page):
    ent = EntertainmentService()
    ent.funny_enabled = True
    presenter = _make_presenter(mock_page, ent)
    buttons = [MagicMock(), MagicMock()]
    presenter.update_funny_visibility(buttons)
    for btn in buttons:
        assert btn.visible is True
        btn.update.assert_called_once()


def test_update_funny_visibility_noop_without_service(mock_page):
    presenter = _make_presenter(mock_page, None)
    buttons = [MagicMock()]
    presenter.update_funny_visibility(buttons)
    buttons[0].update.assert_not_called()


def test_handle_post_save_default_message(mock_page):
    presenter = _make_presenter(mock_page, None)
    presenter.handle_post_save([RowData(), RowData()])
    assert presenter._save_text.value == "Saved"
    assert presenter._save_text.color == ft.Colors.GREEN


def test_handle_post_save_fun_message(mock_page):
    ent = EntertainmentService()
    ent.fun_save_messages = True
    presenter = _make_presenter(mock_page, ent)
    presenter.handle_post_save([RowData()])
    assert presenter._save_text.value in FUN_SAVE_MESSAGES
    assert presenter._save_text.color == ft.Colors.GREEN


def test_lucky_phrase_falls_back_without_service(mock_page):
    presenter = _make_presenter(mock_page, None)
    assert presenter.lucky_phrase() == "Done!"


def test_lucky_phrase_uses_service(mock_page):
    ent = EntertainmentService()
    presenter = _make_presenter(mock_page, ent)
    assert bool(presenter.lucky_phrase())


def test_show_stats_dialog_shows_dialog(mock_page):
    ent = EntertainmentService()
    presenter = _make_presenter(mock_page, ent)
    presenter.show_stats_dialog()
    mock_page.show_dialog.assert_called_once()


def test_show_stats_dialog_noop_without_service(mock_page):
    presenter = _make_presenter(mock_page, None)
    presenter.show_stats_dialog()
    mock_page.show_dialog.assert_not_called()


def test_on_field_change_records_edit(mock_page):
    ent = EntertainmentService()
    presenter = _make_presenter(mock_page, ent)
    e = MagicMock()
    e.control.data = "nominal"
    presenter.on_field_change(e)
    assert ent.total_edits == 1
    assert ent.edit_stats.get("nominal") == 1


def test_check_easter_egg_opens_dialog(mock_page):
    ent = EntertainmentService()
    presenter = _make_presenter(mock_page, ent)
    presenter.check_easter_egg("Unicorn Meat")
    assert mock_page.show_dialog.call_count >= 1


def test_check_easter_egg_noop_without_service(mock_page):
    presenter = _make_presenter(mock_page, None)
    presenter.check_easter_egg("anything")
    mock_page.show_dialog.assert_not_called()


def test_check_icon_switches_to_pets_in_cat_mode(mock_page):
    ent = EntertainmentService()
    presenter = _make_presenter(mock_page, ent)
    assert presenter.check_icon() == ft.Icons.CHECK
    ent.cat_mode = True
    assert presenter.check_icon() == ft.Icons.PETS


def test_handle_post_save_terminal_mode_runs_task(mock_page):
    ent = EntertainmentService()
    ent.terminal_mode = True
    presenter = _make_presenter(mock_page, ent)
    presenter.handle_post_save([RowData()])
    mock_page.run_task.assert_any_call(presenter.show_terminal_save, 1)


def test_handle_post_save_meme_and_cat_run_tasks(mock_page):
    ent = EntertainmentService()
    ent.show_meme_on_save = True
    ent.cat_mode = True
    presenter = _make_presenter(mock_page, ent)
    presenter.handle_post_save([RowData()])
    mock_page.run_task.assert_any_call(presenter.show_meme_dialog)
    mock_page.run_task.assert_any_call(presenter.show_meow_popup)


@patch("asyncio.sleep")
async def test_cycle_tip_rotates_tips(mock_sleep, mock_page):
    mock_sleep.side_effect = [None, asyncio.CancelledError()]
    presenter = _make_presenter(mock_page, None)
    tips = ["one", "two", "three"]
    await presenter.cycle_tip(tips)
    assert mock_sleep.call_count >= 2


@patch("asyncio.sleep")
async def test_cycle_tip_uses_cat_tips(mock_sleep, mock_page):
    ent = EntertainmentService()
    ent.cat_mode = True
    mock_sleep.side_effect = [None, asyncio.CancelledError()]
    presenter = _make_presenter(mock_page, ent)
    await presenter.cycle_tip(["plain"])
    assert mock_sleep.call_count >= 2


@patch("asyncio.sleep")
async def test_show_meow_popup_appends_and_removes(mock_sleep, mock_page):
    presenter = _make_presenter(mock_page, None)
    await presenter.show_meow_popup()
    mock_page.overlay.append.assert_called_once()
    mock_page.overlay.remove.assert_called_once()
    mock_page.update.assert_called()
    mock_sleep.assert_called_once()


@patch("asyncio.sleep")
async def test_show_terminal_save_writes_lines(mock_sleep, mock_page):
    presenter = _make_presenter(mock_page, None)
    await presenter.show_terminal_save(3)
    assert presenter._save_text.value == "Saved"
    assert presenter._save_text.color == ft.Colors.GREEN
    assert presenter._save_text.font_family is None
    assert mock_sleep.call_count == 5


@patch("asyncio.sleep")
async def test_show_meme_dialog_shows_dialog(mock_sleep, mock_page):
    presenter = _make_presenter(mock_page, None)

    class _Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return b'{"url": "http://example.com/meme.png"}'

    with patch.object(
        urllib.request, "urlopen", return_value=_Response()
    ) as urlopen:
        await presenter.show_meme_dialog()
    urlopen.assert_called_once()
    mock_page.show_dialog.assert_called_once()


@patch("asyncio.sleep")
async def test_show_meme_dialog_handles_fetch_failure(mock_sleep, mock_page):
    presenter = _make_presenter(mock_page, None)
    with patch.object(
        urllib.request, "urlopen", side_effect=OSError("no network")
    ):
        await presenter.show_meme_dialog()
    mock_page.show_dialog.assert_not_called()


@patch("asyncio.sleep")
async def test_show_achievement_fireworks_shows_dialog(mock_sleep, mock_page):
    presenter = _make_presenter(mock_page, None)
    await presenter.show_achievement_fireworks(10, "Prolific Editor")
    mock_page.show_dialog.assert_called_once()
    assert mock_sleep.call_count == 15


def test_on_field_change_tracks_edit_stat(mock_page):
    ent = EntertainmentService()
    presenter = _make_presenter(mock_page, ent)
    e = MagicMock()
    e.control.data = "nominal"
    presenter.on_field_change(e)
    assert ent.edit_stats["nominal"] == 1