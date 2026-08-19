import asyncio
from pathlib import PurePosixPath
from unittest.mock import AsyncMock, MagicMock, patch

import aioftp
import pytest

from connection.ftp_connection import FTPConnection, RemoteNotConnectedError
from exceptions import RemoteAuthError, RemoteConnectionError, RemoteTimeoutError
from models.connection import ConnectionConfig

CLIENT_PATH = "connection.ftp_connection.aioftp.Client"


def make_config(**overrides) -> ConnectionConfig:
    base = {
        "id": "c",
        "protocol": "ftp",
        "host": "example.com",
        "port": 21,
        "username": "deploy",
    }
    base.update(overrides)
    return ConnectionConfig(**base)


def make_environment():
    client = MagicMock()
    client.connect = AsyncMock()
    client.login = AsyncMock()
    client.quit = AsyncMock()
    client.list = AsyncMock(return_value=[])
    client.download = AsyncMock()
    client.upload = AsyncMock()
    return client


@pytest.mark.asyncio
async def test_connect_success():
    client = make_environment()
    ftp = FTPConnection(make_config(), password="secret")
    with patch(CLIENT_PATH, return_value=client):
        await ftp.connect()
    client.connect.assert_awaited_once_with("example.com", 21)
    client.login.assert_awaited_once_with("deploy", "secret")
    assert ftp.connected


@pytest.mark.asyncio
async def test_connect_uses_configured_port():
    client = make_environment()
    ftp = FTPConnection(make_config(port=2121))
    with patch(CLIENT_PATH, return_value=client):
        await ftp.connect()
    client.connect.assert_awaited_once_with("example.com", 2121)


@pytest.mark.asyncio
async def test_connect_timeout_raises_remote_timeout():
    client = make_environment()
    client.connect = AsyncMock(side_effect=asyncio.TimeoutError)
    ftp = FTPConnection(make_config())
    with patch(CLIENT_PATH, return_value=client), pytest.raises(RemoteTimeoutError):
        await ftp.connect()
    assert not ftp.connected


@pytest.mark.asyncio
async def test_connect_auth_error_raises_remote_auth():
    client = make_environment()
    client.login = AsyncMock(
        side_effect=aioftp.StatusCodeError(("2xx",), 530, "bad login")
    )
    ftp = FTPConnection(make_config(), password="wrong")
    with patch(CLIENT_PATH, return_value=client), pytest.raises(RemoteAuthError):
        await ftp.connect()
    assert not ftp.connected


@pytest.mark.asyncio
async def test_connect_os_error_raises_remote_connection():
    client = make_environment()
    client.connect = AsyncMock(side_effect=OSError("refused"))
    ftp = FTPConnection(make_config())
    with patch(CLIENT_PATH, return_value=client), pytest.raises(RemoteConnectionError):
        await ftp.connect()
    assert not ftp.connected


@pytest.mark.asyncio
async def test_list_files_returns_names():
    client = make_environment()
    client.list = AsyncMock(return_value=[(PurePosixPath("types.xml"), MagicMock())])
    ftp = FTPConnection(make_config())
    with patch(CLIENT_PATH, return_value=client):
        await ftp.connect()
    names = await ftp.list_files("/db")
    client.list.assert_awaited_once_with("/db")
    assert names == ["types.xml"]


@pytest.mark.asyncio
async def test_download_file():
    client = make_environment()
    ftp = FTPConnection(make_config())
    with patch(CLIENT_PATH, return_value=client):
        await ftp.connect()
    await ftp.download_file("/db/types.xml", "/local/types.xml")
    client.download.assert_awaited_once_with("/db/types.xml", "/local/types.xml")


@pytest.mark.asyncio
async def test_upload_file():
    client = make_environment()
    ftp = FTPConnection(make_config())
    with patch(CLIENT_PATH, return_value=client):
        await ftp.connect()
    await ftp.upload_file("/local/types.xml", "/db/types.xml")
    client.upload.assert_awaited_once_with("/local/types.xml", "/db/types.xml")


@pytest.mark.asyncio
async def test_not_connected_raises():
    ftp = FTPConnection(make_config())
    with pytest.raises(RemoteNotConnectedError):
        await ftp.list_files("/db")


@pytest.mark.asyncio
async def test_disconnect_quits_and_clears():
    client = make_environment()
    ftp = FTPConnection(make_config())
    with patch(CLIENT_PATH, return_value=client):
        await ftp.connect()
        assert ftp.connected
        await ftp.disconnect()
    client.quit.assert_awaited_once()
    assert not ftp.connected


@pytest.mark.asyncio
async def test_double_disconnect_safe():
    ftp = FTPConnection(make_config())
    await ftp.disconnect()
    await ftp.disconnect()
