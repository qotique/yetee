from __future__ import annotations

import asyncio
import logging
from typing import Any

import asyncssh

from exceptions import RemoteAuthError, RemoteConnectionError, RemoteTimeoutError
from models.connection import ConnectionConfig
from protocols import IRemoteConnection

logger = logging.getLogger(__name__)

DEFAULT_SSH_PORT = 22
CONNECT_TIMEOUT = 30


class RemoteNotConnectedError(RemoteConnectionError):
    """Raised when an operation is attempted before connecting."""


class SSHConnection(IRemoteConnection):
    def __init__(self, config: ConnectionConfig, password: str | None = None) -> None:
        self._config = config
        self._password = password
        self._conn: Any = None
        self._sftp: Any = None
        self._connected = False

    @property
    def connected(self) -> bool:
        return self._connected

    async def connect(self) -> None:
        port = DEFAULT_SSH_PORT if self._config.port <= 0 else self._config.port
        kwargs: dict[str, Any] = {
            "host": self._config.host,
            "port": port,
            "username": self._config.username,
            "connect_timeout": CONNECT_TIMEOUT,
        }
        if self._config.key_path:
            kwargs["client_keys"] = [self._config.key_path]
            if self._password:
                kwargs["passphrase"] = self._password
        elif self._password:
            kwargs["password"] = self._password
        print(f"[diag SSH] connect kwargs: { {k: v for k, v in kwargs.items() if k not in ('password', 'passphrase', 'client_keys')} }")
        print(f"[diag SSH] key_path={self._config.key_path!r} has_password={bool(self._password)}")
        try:
            print("[diag SSH] awaiting asyncssh.connect()...")
            conn = await asyncssh.connect(**kwargs)
            print("[diag SSH] asyncssh.connect() returned")
            sftp = await conn.start_sftp_client()
            print("[diag SSH] sftp client started")
        except (asyncio.TimeoutError, TimeoutError) as exc:
            self._connected = False
            print(f"[diag SSH] TIMEOUT: {exc!r}")
            logger.error("SSH connect to %s timed out", self._config.host)
            raise RemoteTimeoutError(
                f"SSH connection to {self._config.host} timed out"
            ) from exc
        except asyncssh.PermissionDenied as exc:
            self._connected = False
            print(f"[diag SSH] AUTH FAILED (PermissionDenied): {exc!r}")
            logger.error("SSH authentication failed for %s", self._config.host)
            raise RemoteAuthError(
                f"SSH authentication failed for {self._config.username}"
            ) from exc
        except (asyncssh.Error, OSError) as exc:
            self._connected = False
            print(f"[diag SSH] CONNECT FAILED: {type(exc).__name__}: {exc!r}")
            logger.error("SSH connect to %s failed: %s", self._config.host, exc)
            raise RemoteConnectionError(
                f"SSH connection to {self._config.host} failed"
            ) from exc
        self._conn = conn
        self._sftp = sftp
        self._connected = True
        print("[diag SSH] connect() done, connected=True")

    async def disconnect(self) -> None:
        if self._conn is not None:
            try:
                self._conn.close()
                await self._conn.wait_closed()
            except (asyncssh.Error, OSError) as exc:
                logger.warning("Error closing SSH connection: %s", exc)
            self._conn = None
        self._sftp = None
        self._connected = False

    async def list_files(self, path: str) -> list[str]:
        self._require_connected()
        try:
            names = await self._sftp.listdir(path)
            return list(names)
        except (asyncssh.Error, OSError) as exc:
            raise RemoteConnectionError(f"Failed to list {path}") from exc

    async def download_file(self, remote_path: str, local_path: str) -> None:
        self._require_connected()
        try:
            await self._sftp.get(remote_path, local_path)
        except (asyncssh.Error, OSError) as exc:
            raise RemoteConnectionError(
                f"Failed to download {remote_path}"
            ) from exc

    async def upload_file(self, local_path: str, remote_path: str) -> None:
        self._require_connected()
        try:
            await self._sftp.put(local_path, remote_path)
        except (asyncssh.Error, OSError) as exc:
            raise RemoteConnectionError(f"Failed to upload {remote_path}") from exc

    def _require_connected(self) -> None:
        if not self._connected:
            raise RemoteNotConnectedError("Connection is not established")