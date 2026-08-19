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

EXPANSION_FILE_EXTENSIONS: tuple[str, ...] = (".json", ".xml", ".txt")


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

    def get_expansion_files(self, economy_dir: str) -> dict[str, str]:
        """Collect mission-side `expansion/**` files into a flat label map.

        Each label is prefixed with `Mission/` and preserves the real relative
        path under the expansion dir (e.g. ``Mission/settings/BaseBuildingSettings.json``)
        so files in different top-level dirs never collide.
        """
        expansion_dir = os.path.join(economy_dir, "expansion")
        if not os.path.isdir(expansion_dir):
            return {}
        out: dict[str, str] = {}
        try:
            entries = sorted(os.listdir(expansion_dir))
        except OSError as ex:
            logger.warning("Could not list expansion dir %s: %s", expansion_dir, ex)
            return {}
        for entry in entries:
            if entry.startswith("."):
                continue
            area_dir = os.path.join(expansion_dir, entry)
            if not os.path.isdir(area_dir):
                continue
            self._collect_expansion_files(area_dir, f"Mission/{entry}", out)
        return out

    def _collect_expansion_files(
        self,
        directory: str,
        prefix: str,
        out: dict[str, str],
    ) -> None:
        try:
            entries = sorted(os.listdir(directory))
        except OSError as ex:
            logger.warning("Could not list dir %s: %s", directory, ex)
            return
        for entry in entries:
            if entry.startswith("."):
                continue
            path = os.path.join(directory, entry)
            if os.path.isdir(path):
                self._collect_expansion_files(path, f"{prefix}/{entry}", out)
            elif entry.lower().endswith(EXPANSION_FILE_EXTENSIONS):
                out[f"{prefix}/{entry}".lstrip("/")] = path
