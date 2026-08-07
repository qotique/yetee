from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from exceptions import AccessError
from models.connection import ConnectionConfig

logger = logging.getLogger(__name__)

DEFAULT_CONNECTIONS_FILE = str(Path.home() / ".yetee" / "connections.json")


class ConnectionRepository:
    def __init__(self, path: str = DEFAULT_CONNECTIONS_FILE) -> None:
        self._path = path

    def load(self) -> tuple[list[ConnectionConfig], str | None]:
        if not os.path.exists(self._path):
            return [], None
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                data = json.load(f)
            active_id: str | None = None
            raw_configs: list[object] = []
            if isinstance(data, dict):
                active_raw = data.get("active_id")
                active_id = str(active_raw) if active_raw else None
                raw_configs = data.get("connections", [])
            elif isinstance(data, list):
                raw_configs = data
            configs = [
                ConnectionConfig.from_dict(c)
                for c in raw_configs
                if isinstance(c, dict)
            ]
            return configs, active_id
        except (json.JSONDecodeError, OSError) as ex:
            logger.warning("Failed to load connections: %s", ex)
            return [], None

    def save(self, connections: list[ConnectionConfig], active_id: str | None) -> None:
        directory = os.path.dirname(self._path)
        try:
            os.makedirs(directory, exist_ok=True)
            data = {
                "active_id": active_id,
                "connections": [c.to_dict() for c in connections],
            }
            with open(self._path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except OSError as ex:
            logger.error("Failed to save connections: %s", ex)
            raise AccessError(f"Cannot save connections: {ex}") from ex