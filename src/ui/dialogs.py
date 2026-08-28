from __future__ import annotations

import flet as ft


def show_message(page: ft.Page, title: str, message: str) -> None:
    dialog = ft.AlertDialog(
        title=ft.Text(title),
        content=ft.Text(message),
        actions=[
            ft.TextButton("OK", on_click=lambda _: page.pop_dialog()),
        ],
    )
    page.show_dialog(dialog)
    page.update()


def show_error(page: ft.Page, message: str) -> None:
    show_message(page, "Error", message)
