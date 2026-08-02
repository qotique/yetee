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

ECONOMY_DIR_FILES: list[str] = [
    "cfgeventspawns.xml",
]


class EconomyService:
    def find_config(self, economy_dir: str) -> str | None:
        path = os.path.join(economy_dir, "cfgeconomycore.xml")
        return path if os.path.exists(path) else None

    def get_type_files(self, economy_dir: str) -> dict[str, str]:
        config_path = self.find_config(economy_dir)
        if config_path is None:
            return {}
        try:
            tree = ET.parse(config_path)
            root = tree.getroot()
            ce = root.find("ce")
            if ce is not None:
                folder = ce.get("folder", "")
                types_dir = os.path.join(economy_dir, folder) if folder else economy_dir
                files: dict[str, str] = {}
                for file_elem in ce.findall("file"):
                    name = file_elem.get("name", "")
                    if name:
                        files[name] = os.path.join(types_dir, name)
                return files
            return {}
        except ET.ParseError as ex:
            raise ParseError(f"Failed to parse {config_path}: {ex}") from ex
        except FileNotFoundError as ex:
            raise AccessError(f"File not found: {config_path}") from ex

    def get_types_dir(self, economy_dir: str) -> str:
        config_path = self.find_config(economy_dir)
        if config_path is None:
            return economy_dir
        try:
            tree = ET.parse(config_path)
            root = tree.getroot()
            ce = root.find("ce")
            if ce is not None:
                folder = ce.get("folder", "")
                return os.path.join(economy_dir, folder) if folder else economy_dir
            return economy_dir
        except Exception as ex:
            logger.warning("Could not get types dir from %s: %s", config_path, ex)
            return economy_dir

    def get_known_files(self, directory: str) -> dict[str, str]:
        files: dict[str, str] = {}
        for filename in ECONOMY_FILES:
            path = os.path.join(directory, filename)
            if os.path.exists(path):
                files[filename] = path
        return files

    def get_all_editable_files(self, economy_dir: str) -> dict[str, str]:
        files: dict[str, str] = {}
        files.update(self.get_type_files(economy_dir))
        types_dir = self.get_types_dir(economy_dir)
        if types_dir:
            files.update(self.get_known_files(types_dir))
        return files

    def get_economy_dir_files(self, economy_dir: str) -> dict[str, str]:
        files: dict[str, str] = {}
        for filename in ECONOMY_DIR_FILES:
            path = os.path.join(economy_dir, filename)
            if os.path.exists(path):
                files[filename] = path
        return files
