from __future__ import annotations

import logging
import os

from lxml import etree as ET

from exceptions import ParseError, AccessError

logger = logging.getLogger(__name__)

ECONOMY_FILES: dict[str, str] = {
    "events.xml": "Events",
    "globals.xml": "Globals",
    "cfgspawnabletypes.xml": "Spawnable Types",
    "cfgrandompresets.xml": "Random Presets",
}


class EconomyService:
    def get_type_files(self, config_path: str) -> dict[str, str]:
        files: dict[str, str] = {}
        try:
            tree = ET.parse(config_path)
            root = tree.getroot()
            ce = root.find("ce")
            if ce is not None:
                folder = ce.get("folder", "")
                config_dir = os.path.dirname(config_path)
                types_dir = os.path.join(config_dir, folder) if folder else config_dir
                for file_elem in ce.findall("file"):
                    name = file_elem.get("name", "")
                    if name:
                        files[name] = os.path.join(types_dir, name)
            return files
        except ET.ParseError as ex:
            raise ParseError(f"Failed to parse {config_path}: {ex}") from ex
        except FileNotFoundError as ex:
            raise AccessError(f"File not found: {config_path}") from ex

    def get_types_dir(self, config_path: str) -> str | None:
        try:
            tree = ET.parse(config_path)
            root = tree.getroot()
            ce = root.find("ce")
            if ce is not None:
                folder = ce.get("folder", "")
                config_dir = os.path.dirname(config_path)
                return os.path.join(config_dir, folder) if folder else config_dir
            return os.path.dirname(config_path)
        except Exception as ex:
            logger.warning("Could not get types dir from %s: %s", config_path, ex)
            return None

    def get_known_files(self, directory: str) -> dict[str, str]:
        files: dict[str, str] = {}
        for filename in ECONOMY_FILES:
            path = os.path.join(directory, filename)
            if os.path.exists(path):
                files[filename] = path
        return files

    def get_all_editable_files(self, config_path: str) -> dict[str, str]:
        files: dict[str, str] = {}
        files.update(self.get_type_files(config_path))
        types_dir = self.get_types_dir(config_path)
        if types_dir:
            files.update(self.get_known_files(types_dir))
        return files
