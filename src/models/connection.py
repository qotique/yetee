from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ConnectionConfig:
    id: str
    protocol: str
    host: str
    port: int
    username: str
    key_path: str = ""
    remote_economy_dir: str = ""
    remote_profiles_dir: str = ""
    project_name: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "protocol": self.protocol,
            "host": self.host,
            "port": self.port,
            "username": self.username,
            "key_path": self.key_path,
            "remote_economy_dir": self.remote_economy_dir,
            "remote_profiles_dir": self.remote_profiles_dir,
            "project_name": self.project_name,
        }

    @classmethod
    def from_dict(cls, d: dict[str, object]) -> ConnectionConfig:
        return cls(
            id=str(d.get("id", "")),
            protocol=str(d.get("protocol", "")),
            host=str(d.get("host", "")),
            port=int(str(d.get("port", 0))),
            username=str(d.get("username", "")),
            key_path=str(d.get("key_path", "")),
            remote_economy_dir=str(d.get("remote_economy_dir", "")),
            remote_profiles_dir=str(d.get("remote_profiles_dir", "")),
            project_name=str(d.get("project_name", "")),
        )