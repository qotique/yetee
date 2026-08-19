from __future__ import annotations

import asyncio
import logging
from typing import Any

import aioftp

from exceptions import (
    RemoteAuthError,
    RemoteConnectionError,
    RemoteTimeoutError,
)
from models.connection import ConnectionConfig
from protocols import IRemoteConnection

logger = logging.getLogger(__name__)

DEFAULT_FTP_PORT = 21


class RemoteNotConnectedError(RemoteConnectionError):
    """Raised when an operation is attempted before connecting."""


class FTPConnection(IRemoteConnection):
    def __init__(self, config: ConnectionConfig, password: str | None = None) -> None:
        self._config = config
        self._password = password or ""
        self._client: Any = None
        self._connected = False

    @property
    def connected(self) -> bool:
        return self._connected

    async def connect(self) -> None:
        if self._connected:
            return
        port = DEFAULT_FTP_PORT if self._config.port <= 0 else self._config.port
        client: Any = aioftp.Client()
        print(
            f"[diag FTP] connect kwargs: host={self._config.host} port={port} "
            f"user={self._config.username} has_password={bool(self._password)}"
        )
        try:
            print("[diag FTP] awaiting aioftp connect()...")
            await client.connect(self._config.host, port)
            print("[diag FTP] connected, awaiting login()...")
            await client.login(self._config.username, self._password)
            print("[diag FTP] login OK")
        except (asyncio.TimeoutError, TimeoutError) as exc:
            self._connected = False
            print(f"[diag FTP] TIMEOUT: {exc!r}")
            logger.error("FTP connect to %s timed out", self._config.host)
            raise RemoteTimeoutError(
                f"FTP connection to {self._config.host} timed out"
            ) from exc
        except (aioftp.StatusCodeError, aioftp.AIOFTPException) as exc:
            self._connected = False
            print(f"[diag FTP] LOGIN FAILED: {type(exc).__name__}: {exc!r}")
            logger.error(
                "FTP authentication failed for %s@%s",
                self._config.username,
                self._config.host,
            )
            raise RemoteAuthError(
                f"FTP authentication failed for {self._config.username}"
            ) from exc
        except OSError as exc:
            self._connected = False
            print(f"[diag FTP] CONNECT FAILED: {type(exc).__name__}: {exc!r}")
            logger.error("FTP connect to %s failed: %s", self._config.host, exc)
            raise RemoteConnectionError(
                f"FTP connection to {self._config.host} failed"
            ) from exc
        self._client = client
        self._connected = True
        print("[diag FTP] connect() done, connected=True")

    async def disconnect(self) -> None:
        if self._client is not None:
            try:
                await self._client.quit()
            except (aioftp.AIOFTPException, OSError) as exc:
                logger.warning("Error closing FTP connection: %s", exc)
        self._client = None
        self._connected = False

    async def list_files(self, path: str) -> list[str]:
        self._require_connected()
        try:
            entries = await self._client.list(path)
            names: list[str] = []
            for entry, _info in entries:
                names.append(str(entry.name))
            return names
        except (aioftp.AIOFTPException, OSError) as exc:
            raise RemoteConnectionError(f"Failed to list {path}") from exc

    async def download_file(self, remote_path: str, local_path: str) -> None:
        self._require_connected()
        try:
            await self._client.download(remote_path, local_path)
        except (aioftp.AIOFTPException, OSError) as exc:
            raise RemoteConnectionError(f"Failed to download {remote_path}") from exc

    async def upload_file(self, local_path: str, remote_path: str) -> None:
        self._require_connected()
        try:
            await self._client.upload(local_path, remote_path)
        except (aioftp.AIOFTPException, OSError) as exc:
            raise RemoteConnectionError(f"Failed to upload {remote_path}") from exc

    def _require_connected(self) -> None:
        if not self._connected:
            raise RemoteNotConnectedError("Connection is not established")
