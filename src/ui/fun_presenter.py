from __future__ import annotations

import asyncio
import json
import logging
import random
import urllib.request
from typing import cast

from models.row_data import RowData
from services.entertainment_service import EntertainmentService

import flet as ft

logger = logging.getLogger(__name__)


class FunPresenter:
    def __init__(
        self,
        page: ft.Page,
        entertainment_service: EntertainmentService | None,
        tips_switcher: ft.AnimatedSwitcher,
        save_text: ft.Text,
    ) -> None:
        self._page = page
        self._ent = entertainment_service
        self._tips_switcher = tips_switcher
        self._save_text = save_text

    def _pet_icon(self) -> ft.Icons:
        return cast(ft.Icons, ft.Icons.PETS)

    def is_cat(self) -> bool:
        return bool(self._ent and self._ent.cat_mode)

    def icon_for(self, normal: ft.Icons) -> ft.Icons:
        return self._pet_icon() if self.is_cat() else normal

    def check_icon(self) -> ft.Icons:
        return self._pet_icon() if self.is_cat() else cast(ft.Icons, ft.Icons.CHECK)

    def fab_icon(self, shift_pressed: bool) -> ft.Icons:
        if self.is_cat():
            return self._pet_icon()
        return cast(
            ft.Icons,
            ft.Icons.DELETE if shift_pressed else ft.Icons.ADD,
        )

    def update_funny_visibility(self, buttons: list[ft.Control]) -> None:
        if not self._ent:
            return
        visible = self._ent.funny_enabled
        for btn in buttons:
            btn.visible = visible
            btn.update()

    def on_field_change(self, e: object) -> None:
        if not self._ent:
            return
        if e is not None:
            control = getattr(e, "control", None)
            if control is not None:
                field_key = getattr(control, "data", None)
                if field_key:
                    self._ent.record_edit(field_key)
                    if field_key == "name":
                        name = getattr(control, "value", "")
                        self.check_easter_egg(name)
        achievement = self._ent.check_achievements()
        if achievement is not None:
            name = self._ent.get_achievement_name(achievement)
            if name:
                self._page.run_task(
                    self.show_achievement_fireworks,
                    achievement,
                    name,
                )

    def check_easter_egg(self, name: str) -> None:
        if not self._ent:
            return
        egg = self._ent.check_easter_egg(name)
        if egg:
            msg, color = egg
            dialog = ft.AlertDialog(
                title=ft.Text("Easter Egg Found!", weight=ft.FontWeight.BOLD),
                content=ft.Column(
                    [
                        ft.Text(
                            msg,
                            size=18,
                            weight=ft.FontWeight.BOLD,
                            color=color,
                        ),
                    ],
                    tight=True,
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                actions=[
                    ft.TextButton("Nice!", on_click=lambda _: self._page.pop_dialog())
                ],
                actions_alignment=ft.MainAxisAlignment.CENTER,
            )
            self._page.show_dialog(dialog)
            self._page.update()

    async def cycle_tip(self, tips: list[str]) -> None:
        idx = 0
        while True:
            try:
                await asyncio.sleep(6)
            except asyncio.CancelledError:
                return
            idx = (idx + 1) % len(tips)
            if self._ent and self._ent.cat_mode:
                tip = self._ent.get_cat_tip(idx)
            else:
                tip = tips[idx]
            self._tips_switcher.content = ft.Text(
                tip,
                size=11,
                italic=True,
                color=ft.Colors.GREY_500,
            )
            self._tips_switcher.update()

    async def show_meow_popup(self) -> None:
        meow = ft.Container(
            content=ft.Text(
                "Meow!",
                size=36,
                weight=ft.FontWeight.BOLD,
                color=ft.Colors.PINK_ACCENT,
            ),
            bgcolor=ft.Colors.with_opacity(0.7, ft.Colors.WHITE),
            border_radius=10,
            padding=20,
        )
        self._page.overlay.append(meow)
        self._page.update()
        await asyncio.sleep(0.8)
        try:
            self._page.overlay.remove(meow)
            self._page.update()
        except ValueError:
            pass

    def handle_post_save(self, rows: list[RowData]) -> None:
        if not self._ent:
            self._save_text.value = "Saved"
            self._save_text.color = ft.Colors.GREEN
            return

        if self._ent.terminal_mode:
            self._page.run_task(self.show_terminal_save, len(rows))
        elif self._ent.fun_save_messages:
            self._save_text.value = self._ent.get_fun_save_message()
            self._save_text.color = ft.Colors.GREEN
        else:
            self._save_text.value = "Saved"
            self._save_text.color = ft.Colors.GREEN

        if self._ent.show_meme_on_save:
            self._page.run_task(self.show_meme_dialog)

        if self._ent.cat_mode:
            self._page.run_task(self.show_meow_popup)

    async def show_terminal_save(self, row_count: int) -> None:
        lines = [
            "> Saving types.xml...",
            f"> Parsing {row_count} entries...",
            "> Writing XML...",
            "> Done. 0 errors, 0 warnings.",
        ]
        self._save_text.font_family = "monospace"
        self._save_text.color = ft.Colors.GREEN_ACCENT_700
        output_lines = []
        for line in lines:
            output_lines.append(line)
            self._save_text.value = "\n".join(output_lines)
            self._save_text.update()
            await asyncio.sleep(0.35)
        await asyncio.sleep(2)
        self._save_text.font_family = None
        self._save_text.value = "Saved"
        self._save_text.color = ft.Colors.GREEN
        self._save_text.update()

    async def show_meme_dialog(self) -> None:
        url = None
        try:
            req = urllib.request.Request(
                "https://meme-api.com/gimme",
                headers={"User-Agent": "types-editor/0.2.1"},
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode())
            url = data.get("url") or data.get("preview", [None])[-1]
        except Exception as ex:
            logger.debug("Meme fetch failed: %s", ex)
            return
        if not url:
            return
        dialog = ft.AlertDialog(
            title=ft.Text("Meme of the moment"),
            content=ft.Column(
                [
                    ft.Image(
                        src=url,
                        height=300,
                        fit=ft.ImageFit.CONTAIN,
                    ),
                ],
                tight=True,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            actions=[
                ft.TextButton(
                    "Close",
                    on_click=lambda _: self._page.pop_dialog(),
                )
            ],
        )
        self._page.show_dialog(dialog)
        self._page.update()

    def show_stats_dialog(self) -> None:
        if not self._ent:
            return
        text = self._ent.get_stats_text()
        dialog = ft.AlertDialog(
            title=ft.Text("Edit Statistics", weight=ft.FontWeight.BOLD),
            content=ft.Container(
                content=ft.Text(
                    text,
                    font_family="monospace",
                    size=13,
                ),
                padding=10,
            ),
            actions=[
                ft.TextButton(
                    "Close",
                    on_click=lambda _: self._page.pop_dialog(),
                )
            ],
        )
        self._page.show_dialog(dialog)
        self._page.update()

    def lucky_phrase(self) -> str:
        return self._ent.get_lucky_phrase() if self._ent else "Done!"

    async def show_achievement_fireworks(
        self,
        threshold: int,
        name: str,
    ) -> None:
        chars = ["*", "✦", "✧", "★", "☆"]
        content_text = ft.Text(
            "",
            size=14,
            text_align=ft.TextAlign.CENTER,
            font_family="monospace",
        )
        total = self._ent.total_edits if self._ent else 0
        dialog = ft.AlertDialog(
            title=ft.Text(
                f"Achievement Unlocked: {name}!", weight=ft.FontWeight.BOLD
            ),
            content=ft.Column(
                [
                    ft.Text(f"{total} total edits", size=13, color=ft.Colors.GREY_600),
                    ft.Divider(height=4),
                    content_text,
                ],
                tight=True,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            actions=[
                ft.TextButton("Continue", on_click=lambda _: self._page.pop_dialog())
            ],
            actions_alignment=ft.MainAxisAlignment.CENTER,
        )
        self._page.show_dialog(dialog)
        self._page.update()
        for _ in range(15):
            lines = "\n".join(
                "  " + "".join(random.choice(chars) for _ in range(12)) + "  "
                for _ in range(3)
            )
            content_text.value = lines
            content_text.update()
            await asyncio.sleep(0.15)