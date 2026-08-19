from __future__ import annotations

import logging
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from typing import Any
from uuid import uuid4

import keyring

from connection.connection_factory import create_connection
from models.connection import ConnectionConfig
from protocols import IRemoteConnection
from repository.connection_repository import ConnectionRepository

logger = logging.getLogger(__name__)

KEYCHAIN_SERVICE = "yetee.connections"
_KEYCHAIN_TIMEOUT = 3.0


class ConnectionManager:
    def __init__(
        self,
        repository: ConnectionRepository | None = None,
        keychain: Any = keyring,
    ) -> None:
        self._repository = repository or ConnectionRepository()
        self._keychain = keychain
        self._connections, self._active_id = self._repository.load()

    def list_connections(self) -> list[ConnectionConfig]:
        return list(self._connections)

    def get(self, config_id: str) -> ConnectionConfig | None:
        for cfg in self._connections:
            if cfg.id == config_id:
                return cfg
        return None

    @property
    def active_connection(self) -> ConnectionConfig | None:
        if self._active_id is None:
            return None
        return self.get(self._active_id)

    def add(self, config: ConnectionConfig, password: str = "") -> None:
        if not config.id:
            config.id = uuid4().hex
        self._connections = [c for c in self._connections if c.id != config.id]
        self._connections.append(config)
        if password:
            if not self._set_password(config.id, password):
                print(
                    f"[diag keyring] WARNING: could not store password for {config.id}; "
                    f"proceeding without it (key-based auth still works)"
                )
        self._persist()

    def remove(self, config_id: str) -> None:
        self._connections = [c for c in self._connections if c.id != config_id]
        if self._active_id == config_id:
            self._active_id = None
        self._call(self._delete_password, config_id)
        self._persist()

    def _call(self, fn: Callable[..., object], *args: object) -> None:
        try:
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(fn, *args)
                future.result(timeout=_KEYCHAIN_TIMEOUT)
        except FutureTimeoutError:
            print("[diag keyring] operation timed out (ignored)")
        except Exception as ex:  # noqa: BLE001
            print(f"[diag keyring] operation error: {type(ex).__name__}: {ex!r}")

    def _call_password(self, config_id: str) -> None:
        self._keychain.delete_password(KEYCHAIN_SERVICE, config_id)

    def _call_password_store(self, config_id: str, password: str) -> None:
        self._keychain.set_password(KEYCHAIN_SERVICE, config_id, password)

    def set_active(self, config_id: str | None) -> None:
        if config_id is not None and self.get(config_id) is None:
            raise ValueError(f"Unknown connection id: {config_id}")
        self._active_id = config_id
        self._persist()

    def _set_password(self, config_id: str, password: str) -> bool:
        try:
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(
                    self._keychain.set_password, KEYCHAIN_SERVICE, config_id, password
                )
                future.result(timeout=_KEYCHAIN_TIMEOUT)
            print(f"[diag keyring] password stored for {config_id}")
            return True
        except FutureTimeoutError:
            print(f"[diag keyring] storing password for {config_id} timed out")
            return False
        except Exception as ex:  # noqa: BLE001
            print(f"[diag keyring] storing password for {config_id} failed: {ex!r}")
            return False

    def _delete_password(self, config_id: str) -> None:
        try:
            self._keychain.delete_password(KEYCHAIN_SERVICE, config_id)
        except Exception as ex:  # noqa: BLE001
            logger.debug("No stored secret for %s: %s", config_id, ex)

    def _password(self, config: ConnectionConfig) -> str | None:
        print(f"[diag keyring] reading secret for {config.id}...")
        try:
            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(
                    self._keychain.get_password, KEYCHAIN_SERVICE, config.id
                )
                result = future.result(timeout=_KEYCHAIN_TIMEOUT)
        except FutureTimeoutError:
            print("[diag keyring] read TIMED OUT -> returning None")
            logger.debug("Keyring read for %s timed out", config.id)
            return None
        except Exception as ex:  # noqa: BLE001
            print(f"[diag keyring] read RAISED {type(ex).__name__}: {ex!r}")
            logger.debug("Could not read secret for %s: %s", config.id, ex)
            return None
        print(f"[diag keyring] get_password returned {result is not None}")
        return str(result) if result is not None else None

    def create(self, config: ConnectionConfig) -> IRemoteConnection:
        print(
            f"[diag manager] create({config.protocol}) -> calling _password / factory"
        )
        conn = create_connection(config, self._password(config))
        print(f"[diag manager] created {type(conn).__name__}")
        return conn

    async def connect(self, config: ConnectionConfig) -> None:
        connection = self.create(config)
        await connection.connect()

    async def disconnect(self, config: ConnectionConfig) -> None:
        connection = self.create(config)
        if connection.connected:
            await connection.disconnect()

    def _persist(self) -> None:
        self._repository.save(self._connections, self._active_id)
