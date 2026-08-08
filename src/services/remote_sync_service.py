from __future__ import annotations

import logging
import os

from exceptions import RemoteConnectionError
from lxml import etree as ET
from models.connection import ConnectionConfig
from protocols import IRemoteConnection
from services.connection_manager import ConnectionManager
from services.economy_service import (
    ECONOMY_DIR_FILES,
    ECONOMY_FILES,
    EconomyService,
)

logger = logging.getLogger(__name__)

CONFIG_FILENAME = "cfgeconomycore.xml"


def _join_remote(base_dir: str, name: str) -> str:
    return f"{base_dir.rstrip('/')}/{name}"


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

    async def sync_to_local(
        self,
        config: ConnectionConfig,
        remote_dir: str,
        local_dir: str,
        connection: IRemoteConnection | None = None,
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

            os.makedirs(types_local, exist_ok=True)
            # Files referenced by the CE config (<file name=...>).
            for _name, local_path in self._economy.get_type_files(local_dir).items():
                remote_path = _join_remote(types_remote, os.path.basename(local_path))
                os.makedirs(os.path.dirname(local_path), exist_ok=True)
                await self._download_present(conn, remote_path, local_path)
            # Known economy files that live in the types folder.
            for fname in ECONOMY_FILES:
                await self._download_present(
                    conn,
                    _join_remote(types_remote, fname),
                    os.path.join(types_local, fname),
                )
            # Optional files discovered at the economy root (e.g. cfgeventspawns.xml).
            for fname in ECONOMY_DIR_FILES:
                await self._download_present(
                    conn,
                    _join_remote(remote_dir, fname),
                    os.path.join(local_dir, fname),
                )
        finally:
            if conn.connected:
                await conn.disconnect()

    async def upload_to_remote(
        self,
        config: ConnectionConfig,
        local_dir: str,
        remote_dir: str,
        connection: IRemoteConnection | None = None,
    ) -> None:
        conn = await self._connect(config, connection)
        try:
            for root, _dirs, files in os.walk(local_dir):
                for name in files:
                    local_path = os.path.join(root, name)
                    rel = os.path.relpath(local_path, local_dir)
                    remote_path = _join_remote(remote_dir, rel.replace(os.sep, "/"))
                    print(f"[diag sync] upload {remote_path}")
                    await conn.upload_file(local_path, remote_path)
        finally:
            if conn.connected:
                await conn.disconnect()