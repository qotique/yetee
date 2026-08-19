from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

PROFILE_FILE_EXTENSIONS: tuple[str, ...] = (".xml", ".json", ".txt")


class ProfileService:
    def scan_profiles(self, profiles_dir: str) -> dict[str, dict[str, str]]:
        entities: dict[str, dict[str, str]] = {}
        if not profiles_dir or not os.path.isdir(profiles_dir):
            return entities
        try:
            subdirs = sorted(os.listdir(profiles_dir))
        except OSError as ex:
            logger.warning("Could not list profiles dir %s: %s", profiles_dir, ex)
            return entities
        for entry in subdirs:
            entity_dir = os.path.join(profiles_dir, entry)
            if not os.path.isdir(entity_dir) or entry.startswith("."):
                continue
            files = self._collect_files(entity_dir)
            if files:
                entities[entry] = files
        return entities

    def collect_entity_files(self, directory: str) -> dict[str, str]:
        if not directory or not os.path.isdir(directory):
            return {}
        return self._collect_files(directory)

    def _collect_files(self, directory: str) -> dict[str, str]:
        files: dict[str, str] = {}
        self._collect_files_into(directory, "", files)
        return files

    def _collect_files_into(
        self, directory: str, prefix: str, files: dict[str, str]
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
                sub_prefix = f"{prefix}/{entry}".lstrip("/")
                self._collect_files_into(path, sub_prefix, files)
            elif entry.lower().endswith(PROFILE_FILE_EXTENSIONS):
                key = f"{prefix}/{entry}".lstrip("/")
                files[key] = path
