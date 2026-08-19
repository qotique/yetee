import asyncio
import os

import pytest

from exceptions import RemoteConnectionError

from connection.connection_factory import create_connection, register_connection
from models.connection import ConnectionConfig
from models.project import Project
from protocols import IRemoteConnection
from repository.connection_repository import ConnectionRepository
from services.connection_manager import ConnectionManager
from services.remote_sync_service import RemoteSyncService


class FakeKeychain:
    def __init__(self) -> None:
        self._data: dict[str, str] = {}

    def set_password(self, service: str, username: str, password: str) -> None:
        self._data[f"{service}:{username}"] = password

    def get_password(self, service: str, username: str) -> str | None:
        return self._data.get(f"{service}:{username}")

    def delete_password(self, service: str, username: str) -> None:
        self._data.pop(f"{service}:{username}", None)


class InMemoryConnection(IRemoteConnection):
    _shared: dict[str, str] = {
        "m/mp/cfgeconomycore.xml": (
            '<economy><ce folder="db"><file name="types.xml"/></ce></economy>'
        ),
        "m/mp/db/types.xml": "<types></types>",
        "m/mp/db/events.xml": "<events/>",
        "m/mp/cfgeventspawns.xml": "<spawns/>",
    }

    def __init__(self, config: ConnectionConfig, password: str | None = None) -> None:
        self.config = config
        self.password = password
        self._connected = False
        self.files = InMemoryConnection._shared

    connected = property(lambda self: self._connected)

    async def connect(self) -> None:
        self._connected = True

    async def disconnect(self) -> None:
        self._connected = False

    async def list_files(self, path: str) -> list[str]:
        prefix = path.rstrip("/") + "/"
        names = {
            os.path.basename(p)
            for p in self.files
            if p.startswith(prefix) and "/" not in p[len(prefix) :]
        }
        return sorted(names)

    async def download_file(self, remote_path: str, local_path: str) -> None:
        if remote_path not in self.files:
            raise RemoteConnectionError(remote_path)
        with open(local_path, "w", encoding="utf-8") as f:
            f.write(self.files[remote_path])

    async def upload_file(self, local_path: str, remote_path: str) -> None:
        with open(local_path, "r", encoding="utf-8") as f:
            self.files[remote_path] = f.read()


def make_config(protocol: str = "ssh") -> ConnectionConfig:
    return ConnectionConfig(
        id="c1",
        protocol=protocol,
        host="example.com",
        port=22,
        username="user",
        remote_economy_dir="m/mp",
    )


def test_register_and_create_registry() -> None:
    register_connection("mem", InMemoryConnection)
    config = make_config("mem")
    conn = create_connection(config, "secret")
    assert isinstance(conn, InMemoryConnection)
    assert conn.password == "secret"


def test_create_unknown_protocol_raises() -> None:
    with pytest.raises(ValueError):
        create_connection(make_config("nope"))


def test_create_ssh_default_path() -> None:
    conn = create_connection(make_config("ssh"), "pw")
    assert conn is not None
    assert conn.__class__.__name__ == "SSHConnection"


def test_in_memory_password_passthrough() -> None:
    register_connection("mem", InMemoryConnection)
    conn = create_connection(make_config("mem"), "pw")
    assert isinstance(conn, InMemoryConnection)
    assert conn.password == "pw"


def test_repository_round_trip(tmp_path) -> None:
    repo = ConnectionRepository(str(tmp_path / "connections.json"))
    cfg = make_config()
    repo.save([cfg], "c1")
    loaded, active = repo.load()
    assert len(loaded) == 1
    assert loaded[0].host == "example.com"
    assert active == "c1"


def test_repository_load_missing_returns_empty(tmp_path) -> None:
    repo = ConnectionRepository(str(tmp_path / "nope.json"))
    configs, active = repo.load()
    assert configs == []
    assert active is None


def test_manager_add_persists_secret() -> None:
    repo = ConnectionRepository("/tmp/yetee_test_connections.json")
    if os.path.exists(repo._path):
        os.remove(repo._path)
    try:
        manager = ConnectionManager(repo, FakeKeychain())
        cfg = make_config()
        manager.add(cfg, "hunter2")
        assert manager.get("c1") is not None
        assert manager._password(cfg) == "hunter2"
    finally:
        if os.path.exists(repo._path):
            os.remove(repo._path)


def test_manager_active() -> None:
    manager = ConnectionManager(
        ConnectionRepository("/tmp/yetee_test2.json"), FakeKeychain()
    )
    manager.add(make_config())
    manager.set_active("c1")
    assert manager.active_connection is not None
    assert manager.active_connection.id == "c1"
    manager.set_active(None)
    assert manager.active_connection is None


def test_manager_remove_clears_secret() -> None:
    keychain = FakeKeychain()
    repo = ConnectionRepository("/tmp/yetee_test3.json")
    if os.path.exists(repo._path):
        os.remove(repo._path)
    try:
        manager = ConnectionManager(repo, keychain)
        manager.add(make_config(), "pw")
        manager.remove("c1")
        assert manager.get("c1") is None
        # secret gone
        assert manager._password(make_config()) is None
    finally:
        if os.path.exists(repo._path):
            os.remove(repo._path)


def test_manager_create_injects_password() -> None:
    register_connection("mem", InMemoryConnection)
    manager = ConnectionManager(
        ConnectionRepository("/tmp/yetee_test4.json"), FakeKeychain()
    )
    cfg = make_config("mem")
    manager.add(cfg, "sekret")
    conn = manager.create(cfg)
    assert isinstance(conn, InMemoryConnection)
    assert conn.password == "sekret"


def test_sync_to_local_downloads_economy(tmp_path) -> None:
    register_connection("mem", InMemoryConnection)
    manager = ConnectionManager(
        ConnectionRepository("/tmp/yetee_test5.json"), FakeKeychain()
    )
    cfg = make_config("mem")
    local = tmp_path / "local"
    asyncio.run(RemoteSyncService(manager).sync_to_local(cfg, "m/mp", str(local)))
    assert os.path.exists(local / "cfgeconomycore.xml")
    assert os.path.exists(local / "db" / "types.xml")
    assert os.path.exists(local / "db" / "events.xml")
    assert os.path.exists(local / "cfgeventspawns.xml")


def test_upload_to_remote_writes_back(tmp_path) -> None:
    InMemoryConnection._shared = {
        "m/mp/db/types.xml": "<types></types>",
    }
    register_connection("mem", InMemoryConnection)
    manager = ConnectionManager(
        ConnectionRepository("/tmp/yetee_test6.json"), FakeKeychain()
    )
    cfg = make_config("mem")
    local = tmp_path / "local"
    os.makedirs(local / "db", exist_ok=True)
    with open(local / "db" / "types.xml", "w", encoding="utf-8") as f:
        f.write("<types><x/></types>")
    asyncio.run(RemoteSyncService(manager).upload_to_remote(cfg, str(local), "m/mp"))
    assert InMemoryConnection._shared["m/mp/db/types.xml"] == "<types><x/></types>"


def test_project_remote_fields_round_trip() -> None:
    project = Project(
        name="remote",
        economy_dir="/tmp/ws",
        types_dir="/tmp/ws/db",
        connection_id="c1",
        remote_dir="m/mp",
    )
    assert project.is_remote
    restored = Project.from_dict(project.to_dict())
    assert restored.connection_id == "c1"
    assert restored.remote_dir == "m/mp"
    assert restored.is_remote


def test_project_local_has_no_remote() -> None:
    project = Project(name="local", economy_dir="/x", types_dir="/x/db")
    assert not project.is_remote
    assert Project.from_dict(project.to_dict()).connection_id == ""
