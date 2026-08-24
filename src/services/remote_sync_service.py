from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import Callable

from core.exceptions import RemoteConnectionError
from lxml import etree as ET
from models.connection import ConnectionConfig
from core.protocols import IRemoteConnection
from services.connection_manager import ConnectionManager
from services.economy_service import (
    ECONOMY_DIR_FILES,
    ECONOMY_FILES,
    EconomyService,
)
from services.profile_service import PROFILE_FILE_EXTENSIONS

logger = logging.getLogger(__name__)

CONFIG_FILENAME = "cfgeconomycore.xml"

ProgressCallback = Callable[[int, int], None]


def _join_remote(base_dir: str, name: str) -> str:
    return f"{base_dir.rstrip('/')}/{name}"


def _is_profile_file(name: str) -> bool:
    return name.lower().endswith(PROFILE_FILE_EXTENSIONS)


def _top_level_name(remote_path: str, base_url: str) -> str:
    """Return the first path segment of ``remote_path`` inside ``base_url``."""
    root = base_url.rstrip("/") + "/"
    if not remote_path.startswith(root):
        return remote_path.split("/", 1)[0]
    rest = remote_path[len(root) :]
    return rest.split("/", 1)[0]


def _ce_folder(local_dir: str) -> str:
    """Return the CE types folder (relative) from a local cfgeconomycore.xml."""
    config_path = os.path.join(local_dir, CONFIG_FILENAME)
    if not os.path.exists(config_path):
        return ""
    try:
        tree = ET.parse(config_path)
        ce = tree.getroot().find("ce")
        if ce is not None:
            folder = str(ce.get("folder") or "").strip()
            if folder:
                return folder
    except Exception as ex:  # noqa: BLE001
        logger.warning("Could not read %s: %s", config_path, ex)
    return ""


class RemoteSyncService:
    """Downloads only the files the editor edits (config + types folder + optional
    economy-dir files), never whole remote directories like 'env'."""

    def __init__(self, manager: ConnectionManager) -> None:
        self._manager = manager
        self._economy = EconomyService()

    async def _connect(
        self,
        config: ConnectionConfig,
        connection: IRemoteConnection | None,
    ) -> IRemoteConnection:
        conn = connection or self._manager.create(config)
        if not conn.connected:
            await conn.connect()
        return conn

    async def _download_present(
        self,
        connection: IRemoteConnection,
        remote_path: str,
        local_path: str,
    ) -> bool:
        """Download a single file, returning False when it does not exist remotely."""
        try:
            print(f"[diag sync] download {remote_path}")
            await connection.download_file(remote_path, local_path)
            return True
        except RemoteConnectionError as ex:
            print(f"[diag sync] missing {remote_path}: {ex}")
            return False

    async def _collect_tree_files(
        self,
        connection: IRemoteConnection,
        remote_dir: str,
        local_dir: str,
        on_status: Callable[[str], None] | None = None,
    ) -> list[tuple[str, str]]:
        """Collect ``(remote_path, local_path)`` pairs for a remote tree.

        Children of a directory are probed concurrently so a large tree does
        not stall on sequential round-trips.
        """
        try:
            names = await connection.list_files(remote_dir)
        except RemoteConnectionError as ex:
            logger.warning("Cannot list %s: %s", remote_dir, ex)
            return []
        if on_status:
            on_status(f"Scanning {remote_dir}…")
        pairs: list[tuple[str, str]] = []
        children = [n for n in names if not n.startswith(".")]
        results: list[bool | BaseException] = await asyncio.gather(
            *(self._is_dir(connection, _join_remote(remote_dir, n)) for n in children),
            return_exceptions=True,
        )
        for name, is_dir in zip(children, results):
            remote_child = _join_remote(remote_dir, name)
            local_child = os.path.join(local_dir, name)
            if isinstance(is_dir, Exception):
                pairs.append((remote_child, local_child))
            elif is_dir:
                pairs.extend(
                    await self._collect_tree_files(
                        connection, remote_child, local_child, on_status
                    )
                )
            elif _is_profile_file(name):
                pairs.append((remote_child, local_child))
        return pairs

    @staticmethod
    async def _is_dir(connection: IRemoteConnection, path: str) -> bool:
        try:
            await connection.list_files(path)
            return True
        except RemoteConnectionError:
            return False

    async def sync_to_local(
        self,
        config: ConnectionConfig,
        remote_dir: str,
        local_dir: str,
        connection: IRemoteConnection | None = None,
        remote_profiles_dir: str = "",
        local_profiles_dir: str = "",
        exclude_profiles: set[str] | None = None,
        on_progress: ProgressCallback | None = None,
        on_status: Callable[[str], None] | None = None,
    ) -> None:
        conn = await self._connect(config, connection)
        os.makedirs(local_dir, exist_ok=True)
        try:
            config_local = os.path.join(local_dir, CONFIG_FILENAME)
            await self._download_present(
                conn, _join_remote(remote_dir, CONFIG_FILENAME), config_local
            )

            folder = _ce_folder(local_dir)
            types_local = self._economy.get_types_dir(local_dir)
            types_remote = _join_remote(remote_dir, folder) if folder else remote_dir

            plan: list[tuple[str, str]] = []
            # Files referenced by the CE config (<file name=...>).
            for _name, local_path in self._economy.get_type_files(local_dir).items():
                remote_path = _join_remote(types_remote, os.path.basename(local_path))
                plan.append((remote_path, local_path))
            # Known economy files that live in the types folder.
            for fname in ECONOMY_FILES:
                plan.append(
                    (
                        _join_remote(types_remote, fname),
                        os.path.join(types_local, fname),
                    )
                )
            # Optional files discovered at the economy root (e.g. cfgeventspawns.xml).
            for fname in ECONOMY_DIR_FILES:
                plan.append(
                    (
                        _join_remote(remote_dir, fname),
                        os.path.join(local_dir, fname),
                    )
                )

            profile_pairs: list[tuple[str, str]] = []

            total = len(plan) + 1  # + cfgeconomycore.xml already downloaded
            done = 1
            if on_progress:
                on_progress(done, total)
            for remote_path, local_path in plan:
                os.makedirs(os.path.dirname(local_path), exist_ok=True)
                await self._download_present(conn, remote_path, local_path)
                done += 1
                if on_progress:
                    on_progress(done, total)

            if remote_profiles_dir and local_profiles_dir:
                if on_status:
                    on_status("Scanning profile files…")
                profile_pairs = await self._collect_tree_files(
                    conn, remote_profiles_dir, local_profiles_dir
                )
                if exclude_profiles:
                    profile_pairs = [
                        pair
                        for pair in profile_pairs
                        if _top_level_name(pair[0], remote_profiles_dir)
                        not in exclude_profiles
                    ]
                if on_status:
                    on_status("Downloading profile files…")
                total = len(plan) + 1 + len(profile_pairs)
                for remote_path, local_path in profile_pairs:
                    os.makedirs(os.path.dirname(local_path), exist_ok=True)
                    await self._download_present(conn, remote_path, local_path)
                    done += 1
                    if on_progress:
                        on_progress(done, total)
        finally:
            if conn.connected:
                await conn.disconnect()

    async def upload_to_remote(
        self,
        config: ConnectionConfig,
        local_dir: str,
        remote_dir: str,
        connection: IRemoteConnection | None = None,
        local_profiles_dir: str = "",
        remote_profiles_dir: str = "",
        exclude_profiles: set[str] | None = None,
    ) -> None:
        conn = await self._connect(config, connection)
        try:
            for root, dirs, files in os.walk(local_dir):
                for name in files:
                    local_path = os.path.join(root, name)
                    rel = os.path.relpath(local_path, local_dir)
                    remote_path = _join_remote(remote_dir, rel.replace(os.sep, "/"))
                    print(f"[diag sync] upload {remote_path}")
                    await conn.upload_file(local_path, remote_path)
            if local_profiles_dir and remote_profiles_dir:
                for root, dirs, files in os.walk(local_profiles_dir):
                    if exclude_profiles and root == local_profiles_dir:
                        dirs[:] = [d for d in dirs if d not in exclude_profiles]
                    for name in files:
                        if not _is_profile_file(name):
                            continue
                        local_path = os.path.join(root, name)
                        rel = os.path.relpath(local_path, local_profiles_dir)
                        remote_path = _join_remote(
                            remote_profiles_dir, rel.replace(os.sep, "/")
                        )
                        print(f"[diag sync] upload {remote_path}")
                        await conn.upload_file(local_path, remote_path)
        finally:
            if conn.connected:
                await conn.disconnect()
