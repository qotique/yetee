import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import asyncssh
import pytest

from connection.ssh_connection import SSHConnection
from exceptions import RemoteAuthError, RemoteConnectionError, RemoteTimeoutError
from models.connection import ConnectionConfig

CONNECT_PATH = "connection.ssh_connection.asyncssh.connect"


def make_config(**overrides) -> ConnectionConfig:
    base = {
        "id": "c",
        "protocol": "ssh",
        "host": "example.com",
        "port": 22,
        "username": "deploy",
    }
    base.update(overrides)
    return ConnectionConfig(**base)


def make_environment():
    sftp = MagicMock()
    conn = MagicMock()
    conn.start_sftp_client = AsyncMock(return_value=sftp)
    conn.close = MagicMock()
    conn.wait_closed = AsyncMock()
    return conn, sftp


@pytest.mark.asyncio
async def test_connect_password_auth():
    conn, _ = make_environment()
    ssh = SSHConnection(make_config(), password="secret")
    with patch(CONNECT_PATH, new=AsyncMock(return_value=conn)) as mock_connect:
        await ssh.connect()
    mock_connect.assert_awaited_once_with(
        host="example.com",
        port=22,
        username="deploy",
        connect_timeout=30,
        password="secret",
    )
    assert ssh.connected
    conn.start_sftp_client.assert_awaited_once()


@pytest.mark.asyncio
async def test_connect_key_auth_with_passphrase():
    conn, _ = make_environment()
    cfg = make_config(key_path="/keys/id_ed25519")
    ssh = SSHConnection(cfg, password="passphrase")
    with patch(CONNECT_PATH, new=AsyncMock(return_value=conn)) as mock_connect:
        await ssh.connect()
    _, kwargs = mock_connect.await_args
    assert kwargs["client_keys"] == ["/keys/id_ed25519"]
    assert kwargs["passphrase"] == "passphrase"
    assert "password" not in kwargs


@pytest.mark.asyncio
async def test_connect_default_port_when_ssh():
    conn, _ = make_environment()
    ssh = SSHConnection(make_config(port=0))
    with patch(CONNECT_PATH, new=AsyncMock(return_value=conn)) as mock_connect:
        await ssh.connect()
    _, kwargs = mock_connect.await_args
    assert kwargs["port"] == 22


@pytest.mark.asyncio
async def test_list_files_uses_sftp_listdir():
    conn, sftp = make_environment()
    sftp.listdir = AsyncMock(return_value=["folder", "types.xml"])
    ssh = SSHConnection(make_config(), password="x")
    with patch(CONNECT_PATH, new=AsyncMock(return_value=conn)):
        await ssh.connect()
        names = await ssh.list_files("/remote")
    assert names == ["folder", "types.xml"]
    sftp.listdir.assert_awaited_once_with("/remote")


@pytest.mark.asyncio
async def test_download_file_uses_sftp_get():
    conn, sftp = make_environment()
    sftp.get = AsyncMock()
    ssh = SSHConnection(make_config(), password="x")
    with patch(CONNECT_PATH, new=AsyncMock(return_value=conn)):
        await ssh.connect()
        await ssh.download_file("/r/ce.xml", "/local/ce.xml")
    sftp.get.assert_awaited_once_with("/r/ce.xml", "/local/ce.xml")


@pytest.mark.asyncio
async def test_upload_file_uses_sftp_put():
    conn, sftp = make_environment()
    sftp.put = AsyncMock()
    ssh = SSHConnection(make_config(), password="x")
    with patch(CONNECT_PATH, new=AsyncMock(return_value=conn)):
        await ssh.connect()
        await ssh.upload_file("/local/ce.xml", "/r/ce.xml")
    sftp.put.assert_awaited_once_with("/local/ce.xml", "/r/ce.xml")


@pytest.mark.asyncio
async def test_disconnect_closes_conn_and_guards_double_close():
    conn, _ = make_environment()
    ssh = SSHConnection(make_config(), password="x")
    with patch(CONNECT_PATH, new=AsyncMock(return_value=conn)):
        await ssh.connect()
        await ssh.disconnect()
        await ssh.disconnect()
    conn.close.assert_called_once()
    conn.wait_closed.assert_awaited_once()
    assert not ssh.connected


@pytest.mark.asyncio
async def test_connect_auth_error_raises_remote_auth_error():
    ssh = SSHConnection(make_config())
    with patch(
        CONNECT_PATH, new=AsyncMock(side_effect=asyncssh.PermissionDenied("denied"))
    ):
        with pytest.raises(RemoteAuthError):
            await ssh.connect()
    assert not ssh.connected


@pytest.mark.asyncio
async def test_connect_timeout_raises_remote_timeout_error():
    ssh = SSHConnection(make_config())
    with patch(CONNECT_PATH, new=AsyncMock(side_effect=asyncio.TimeoutError("late"))):
        with pytest.raises(RemoteTimeoutError):
            await ssh.connect()
    assert not ssh.connected


@pytest.mark.asyncio
async def test_download_oserror_raises_connection_error():
    conn, sftp = make_environment()
    sftp.get = AsyncMock(side_effect=OSError("disk full"))
    ssh = SSHConnection(make_config(), password="x")
    with patch(CONNECT_PATH, new=AsyncMock(return_value=conn)):
        await ssh.connect()
        with pytest.raises(RemoteConnectionError):
            await ssh.download_file("/r/x", "/l/x")
