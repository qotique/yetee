from __future__ import annotations

import os
import time
from dataclasses import dataclass


@dataclass
class Project:
    name: str
    economy_dir: str
    types_dir: str
    profiles_dir: str = ""
    created_at: float = 0.0
    last_opened: float | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "economy_dir": self.economy_dir,
            "types_dir": self.types_dir,
            "profiles_dir": self.profiles_dir,
            "created_at": self.created_at,
            "last_opened": self.last_opened,
        }

    @classmethod
    def from_dict(cls, d: dict[str, object]) -> Project:
        economy_dir = d.get("economy_dir")
        if economy_dir is None:
            config_path = str(d.get("config_path", ""))
            economy_dir = os.path.dirname(config_path) if config_path else ""
        created_at_raw = d.get("created_at", time.time())
        assert isinstance(created_at_raw, (int, float))
        last_opened_raw = d.get("last_opened")
        last_opened: float | None = None
        if last_opened_raw is not None:
            assert isinstance(last_opened_raw, (int, float))
            last_opened = float(last_opened_raw)
        return cls(
            name=str(d.get("name", "")),
            economy_dir=str(economy_dir),
            types_dir=str(d.get("types_dir", "")),
            profiles_dir=str(d.get("profiles_dir", "")),
            created_at=float(created_at_raw),
            last_opened=last_opened,
        )
