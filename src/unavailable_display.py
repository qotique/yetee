from __future__ import annotations

from collections.abc import Callable

import flet as ft

from mod_handlers import get_mod_handler

DEFAULT_MESSAGE = "Editing for this mod is not available yet."


class UnavailableDisplay:
    """Placeholder display for mods whose configs are not yet editable.

    Exposes the ``FileDisplay``-compatible surface (``control``, ``button_row``,
    ``save_current``, ...) so ``EconomyEditor`` can use it as the display for
    entities whose editing is not yet implemented. No file is loaded and every
    save/load method is a no-op.
    """

    def __init__(self, page: ft.Page) -> None:
        self._page = page
        self._entity: str = ""
        self.on_saved: Callable[[], None] | None = None

        self._message = ft.Text(
            DEFAULT_MESSAGE, size=15, italic=True, text_align=ft.TextAlign.CENTER
        )
        content = ft.Container(
            expand=True,
            alignment=ft.Alignment.CENTER,
            content=self._message,
        )
        self.control = ft.Container(
            visible=False,
            expand=True,
            content=content,
        )
        self.button_row = ft.Row(
            [ft.Text("(editor not available for this mod)", size=12, italic=True)],
            alignment=ft.MainAxisAlignment.START,
        )

    def set_entity(self, entity: str) -> None:
        self._entity = entity
        handler = get_mod_handler(entity)
        self._message.value = handler.message if handler else DEFAULT_MESSAGE
        self.control.visible = True

    @property
    def is_dirty(self) -> bool:
        return False

    def load_file(self, path: str) -> None:
        del path

    async def load_file_async(
        self,
        path: str,
        cancel_check: Callable[[], bool] | None = None,
    ) -> None:
        del path, cancel_check

    def save_current(self, e: object = None) -> None:
        del e

    def save_file(self) -> None:
        pass

    def save_async(self) -> None:
        pass

    def clear(self) -> None:
        self._entity = ""
        self.control.visible = False

    def clear_cache(self, path: str) -> None:
        del path