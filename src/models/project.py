from __future__ import annotations

from dataclasses import dataclass
import time


@dataclass
class Project:
    name: str
    config_path: str
    types_dir: str
    created_at: float = 0.0
    last_opened: float | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "config_path": self.config_path,
            "types_dir": self.types_dir,
            "created_at": self.created_at,
            "last_opened": self.last_opened,
        }

    @classmethod
    def from_dict(cls, d: dict[str, object]) -> Project:
        return cls(
            name=str(d.get("name", "")),
            config_path=str(d.get("config_path", "")),
            types_dir=str(d.get("types_dir", "")),
            created_at=float(d.get("created_at", time.time())),
            last_opened=float(d["last_opened"]) if d.get("last_opened") is not None else None,
        )
