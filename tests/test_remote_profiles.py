import asyncio
import os

from exceptions import RemoteConnectionError
from models.connection import ConnectionConfig
from protocols import IRemoteConnection
from services.remote_sync_service import RemoteSyncService


class FakeConnection(IRemoteConnection):
    def __init__(self, files: dict[str, str] | None = None) -> None:
        self.files = files or {}
        self._connected = False

    connected = property(lambda self: self._connected)

    async def connect(self) -> None:
        self._connected = True

    async def disconnect(self) -> None:
        self._connected = False

    async def list_files(self, path: str) -> list[str]:
        prefix = path.rstrip("/") + "/"
        names: set[str] = set()
        for p in self.files:
            if not p.startswith(prefix):
                continue
            rest = p[len(prefix):]
            if "/" in rest:
                names.add(rest.split("/", 1)[0])
            else:
                names.add(rest)
        if names:
            return sorted(names)
        if path in self.files:
            raise RemoteConnectionError(f"not a directory: {path}")
        return []

    async def download_file(self, remote_path: str, local_path: str) -> None:
        os.makedirs(os.path.dirname(local_path), exist_ok=True)
        with open(local_path, "w", encoding="utf-8") as f:
            f.write(self.files[remote_path])

    async def upload_file(self, local_path: str, remote_path: str) -> None:
        with open(local_path, "r", encoding="utf-8") as f:
            self.files[remote_path] = f.read()


class Manager:
    def __init__(self, connection: IRemoteConnection) -> None:
        self._connection = connection

    def create(self, config: ConnectionConfig) -> IRemoteConnection:
        return self._connection


def make_config() -> ConnectionConfig:
    return ConnectionConfig(
        id="c1",
        protocol="mem",
        host="example.com",
        port=22,
        username="user",
        remote_economy_dir="m/mp",
        remote_profiles_dir="profiles",
        project_name="Srv",
    )


def _economy_files() -> dict[str, str]:
    known = {
        "globals.xml": "<globals/>",
        "cfgspawnabletypes.xml": "<spawnable/>",
        "cfgrandompresets.xml": "<presets/>",
    }
    return {
        "m/mp/cfgeconomycore.xml": (
            '<economy><ce folder="db"><file name="types.xml"/></ce></economy>'
        ),
        "m/mp/db/types.xml": "<types></types>",
        "m/mp/db/events.xml": "<events/>",
        "m/mp/cfgeventspawns.xml": "<spawns/>",
        **{f"m/mp/db/{k}": v for k, v in known.items()},
    }


def test_sync_to_local_downloads_profiles(tmp_path) -> None:
    conn = FakeConnection(
        {
            **_economy_files(),
            "profiles/ModA/settings.json": '{"a": 1}',
            "profiles/ModA/readme.txt": "hi",
            "profiles/ModA/server.log": "mod log line",
            "profiles/ModB/deep/nested.xml": "<x/>",
        }
    )
    svc = RemoteSyncService(Manager(conn))
    profiles_local = tmp_path / "profiles"

    asyncio.run(
        svc.sync_to_local(
            make_config(),
            "m/mp",
            str(tmp_path),
            remote_profiles_dir="profiles",
            local_profiles_dir=str(profiles_local),
        )
    )

    assert os.path.exists(profiles_local / "ModA" / "settings.json")
    assert os.path.exists(profiles_local / "ModA" / "readme.txt")
    assert os.path.exists(profiles_local / "ModB" / "deep" / "nested.xml")
    assert not os.path.exists(profiles_local / "ModA" / "server.log")


def test_upload_to_remote_writes_profiles(tmp_path) -> None:
    conn = FakeConnection({})
    svc = RemoteSyncService(Manager(conn))
    local_profiles = tmp_path / "profiles"
    (local_profiles / "ModA").mkdir(parents=True)
    (local_profiles / "ModA" / "cfg.json").write_text('{"x": 5}', encoding="utf-8")
    (local_profiles / "ModA" / "debug.log").write_text("log", encoding="utf-8")

    asyncio.run(
        svc.upload_to_remote(
            make_config(),
            str(tmp_path),
            "m/mp",
            local_profiles_dir=str(local_profiles),
            remote_profiles_dir="profiles",
        )
    )

    assert conn.files["profiles/ModA/cfg.json"] == '{"x": 5}'
    assert "profiles/ModA/debug.log" not in conn.files


def test_sync_profiles_ignores_hidden(tmp_path) -> None:
    conn = FakeConnection(
        {
            **_economy_files(),
            "profiles/ModA/.cache": "keep-out",
            "profiles/ModA/ok.xml": "<ok/>",
        }
    )
    svc = RemoteSyncService(Manager(conn))
    local = tmp_path / "profiles"

    asyncio.run(
        svc.sync_to_local(
            make_config(),
            "m/mp",
            str(tmp_path),
            remote_profiles_dir="profiles",
            local_profiles_dir=str(local),
        )
    )

    assert os.path.exists(local / "ModA" / "ok.xml")
    assert not os.path.exists(local / "ModA" / ".cache")


def test_sync_to_local_reports_progress(tmp_path) -> None:
    conn = FakeConnection(
        {
            **_economy_files(),
            "profiles/ModA/settings.json": '{"a": 1}',
            "profiles/ModA/nested/deep.xml": "<x/>",
        }
    )
    svc = RemoteSyncService(Manager(conn))
    progress: list[tuple[int, int]] = []
    asyncio.run(
        svc.sync_to_local(
            make_config(),
            "m/mp",
            str(tmp_path),
            remote_profiles_dir="profiles",
            local_profiles_dir=str(tmp_path / "profiles"),
            on_progress=lambda done, total: progress.append((done, total)),
        )
    )

    assert progress
    last_done, last_total = progress[-1]
    assert last_done == last_total
    assert progress[0][0] == 1
    assert last_total >= progress[0][1]
    prev_done = 0
    prev_total = 0
    for done, total in progress:
        assert done == prev_done + 1
        assert total >= prev_total
        assert done <= total
        prev_done = done
        prev_total = total


def test_sync_to_local_excludes_profiles(tmp_path) -> None:
    conn = FakeConnection(
        {
            **_economy_files(),
            "profiles/TraderX/traderconfig.json": '{"b": 2}',
            "profiles/CustomMod/cfg.json": '{"a": 1}',
        }
    )
    svc = RemoteSyncService(Manager(conn))
    asyncio.run(
        svc.sync_to_local(
            make_config(),
            "m/mp",
            str(tmp_path),
            remote_profiles_dir="profiles",
            local_profiles_dir=str(tmp_path / "profiles"),
            exclude_profiles={"TraderX"},
        )
    )

    assert os.path.exists(tmp_path / "profiles" / "CustomMod" / "cfg.json")
    assert not os.path.exists(tmp_path / "profiles" / "TraderX" / "traderconfig.json")


def test_upload_to_remote_excludes_profiles(tmp_path) -> None:
    conn = FakeConnection({})
    svc = RemoteSyncService(Manager(conn))
    local_profiles = tmp_path / "profiles"
    (local_profiles / "TraderX").mkdir(parents=True)
    (local_profiles / "TraderX" / "traderconfig.json").write_text('{"b": 2}', encoding="utf-8")
    (local_profiles / "CustomMod").mkdir()
    (local_profiles / "CustomMod" / "cfg.json").write_text('{"a": 1}', encoding="utf-8")

    asyncio.run(
        svc.upload_to_remote(
            make_config(),
            str(tmp_path),
            "m/mp",
            local_profiles_dir=str(local_profiles),
            remote_profiles_dir="profiles",
            exclude_profiles={"TraderX"},
        )
    )

    assert conn.files["profiles/CustomMod/cfg.json"] == '{"a": 1}'
    assert "profiles/TraderX/traderconfig.json" not in conn.files