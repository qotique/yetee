from __future__ import annotations

import asyncio
import json
import logging
import urllib.request

import flet as ft
import webbrowser

from exceptions import NetworkError

logger = logging.getLogger(__name__)

_GITHUB_API = "https://api.github.com/repos/qotique/yetee"


class UpdateService:
    def __init__(self, page: ft.Page) -> None:
        self._page = page

    async def check_for_updates(
        self, current_version: str, show_up_to_date: bool = False
    ) -> None:
        logger.info("Checking for updates (current=%s)", current_version)
        try:
            url = f"{_GITHUB_API}/releases/latest"
            loop = asyncio.get_running_loop()
            response = await loop.run_in_executor(
                None, lambda: urllib.request.urlopen(url, timeout=10)
            )
            data = json.loads(response.read().decode())
            latest_tag = data.get("tag_name", "")
            latest = latest_tag.lstrip("v")

            current_parts = [int(x) for x in current_version.split(".")]
            latest_parts = [int(x) for x in latest.split(".")]

            if latest_parts > current_parts:
                release_notes = data.get("body")
                if not release_notes:
                    release_notes = await self._fetch_commit_message(latest_tag)
                await self._show_update_dialog(
                    latest_tag,
                    data.get("html_url", ""),
                    release_notes or "",
                )
            elif show_up_to_date:
                logger.debug("Already up to date (v%s)", current_version)
                await self._show_up_to_date_dialog(current_version)
        except Exception as ex:
            logger.warning("Update check failed: %s", ex)
            if show_up_to_date:
                await self._show_error_dialog(str(ex))

    async def _fetch_commit_message(self, tag_name: str) -> str | None:
        try:
            loop = asyncio.get_running_loop()

            url = f"{_GITHUB_API}/git/ref/tags/{tag_name}"
            ref_resp = await loop.run_in_executor(
                None, lambda: urllib.request.urlopen(url, timeout=10)
            )
            sha = json.loads(ref_resp.read().decode())["object"]["sha"]

            url = f"{_GITHUB_API}/git/commits/{sha}"
            commit_resp = await loop.run_in_executor(
                None, lambda: urllib.request.urlopen(url, timeout=10)
            )
            result = json.loads(commit_resp.read().decode()).get("message", "")
            assert isinstance(result, str)
            return result
        except Exception as ex:
            logger.debug("Failed to fetch commit message: %s", ex)
            return None

    async def _show_update_dialog(
        self, latest_tag: str, release_url: str, release_notes: str
    ) -> None:
        notes_text = (
            release_notes
            if release_notes
            else "No release notes provided with this release.\n"
            "See the release page on GitHub for details."
        )
        alert = ft.AlertDialog(
            title=ft.Text(f"Update Available: {latest_tag}"),
            content=ft.Text(
                f"Current version: {latest_tag}\n"
                f"Latest version: {latest_tag}\n\n"
                f"--- Release Notes ---\n\n"
                f"{notes_text}",
                selectable=True,
            ),
            actions=[
                ft.TextButton(
                    "Download",
                    on_click=lambda _: (
                        webbrowser.open(release_url),
                        self._page.pop_dialog(),
                    ),
                ),
                ft.TextButton(
                    "Dismiss",
                    on_click=lambda _: self._page.pop_dialog(),
                ),
            ],
            open=True,
        )
        self._page.show_dialog(alert)

    async def _show_up_to_date_dialog(self, current_version: str) -> None:
        alert = ft.AlertDialog(
            title=ft.Text("No Updates"),
            content=ft.Text(f"You have the latest version (v{current_version})."),
            actions=[ft.TextButton("OK", on_click=lambda _: self._page.pop_dialog())],
            open=True,
        )
        self._page.show_dialog(alert)

    async def _show_error_dialog(self, error_msg: str) -> None:
        alert = ft.AlertDialog(
            title=ft.Text("Check Failed"),
            content=ft.Text(f"Could not check for updates:\n{error_msg}"),
            actions=[ft.TextButton("OK", on_click=lambda _: self._page.pop_dialog())],
            open=True,
        )
        self._page.show_dialog(alert)
