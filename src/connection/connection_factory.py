from __future__ import annotations

from collections.abc import Callable

from connection.ftp_connection import FTPConnection
from connection.ssh_connection import SSHConnection
from models.connection import ConnectionConfig
from protocols import IRemoteConnection


_REGISTRY: dict[str, Callable[..., IRemoteConnection]] = {
    "ssh": SSHConnection,
    "ftp": FTPConnection,
}


def register_connection(
    protocol: str,
    factory: Callable[..., IRemoteConnection],
) -> None:
    _REGISTRY[protocol] = factory


def create_connection(
    config: ConnectionConfig, password: str | None = None
) -> IRemoteConnection:
    factory = _REGISTRY.get(config.protocol)
    if factory is None:
        raise ValueError(f"Unsupported connection protocol: {config.protocol}")
    return factory(config=config, password=password)
