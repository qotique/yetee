from __future__ import annotations

import logging
import os

from lxml import etree as ET

from exceptions import ParseError, AccessError

logger = logging.getLogger(__name__)


TYPES_TEMPLATE = """<?xml version="1.0" encoding="UTF-8" standalone="yes" ?>
<types>
</types>
"""


class ConfigService:
    def __init__(self) -> None:
        pass

    def load_files(self, ce_path: str) -> list[str]:
        logger.info("Loading files from config: %s", ce_path)
        files: list[str] = []
        try:
            tree = ET.parse(ce_path)
            root = tree.getroot()
            ce = root.find("ce")
            if ce is not None:
                for file_elem in ce.findall("file"):
                    name = file_elem.get("name", "")
                    if name:
                        files.append(name)
            logger.debug("Found %d files in config", len(files))
            return files
        except ET.ParseError as ex:
            logger.error("Failed to parse config %s: %s", ce_path, ex)
            raise ParseError(f"Failed to parse config: {ex}") from ex
        except FileNotFoundError as ex:
            logger.error("Config not found: %s", ce_path)
            raise AccessError(f"Config file not found: {ce_path}") from ex
        except Exception as ex:
            logger.error("Error loading config %s: %s", ce_path, ex)
            raise AccessError(f"Cannot read config: {ex}") from ex

    def get_ce_element(self, ce_path: str) -> ET.Element | None:
        try:
            tree = ET.parse(ce_path)
            root = tree.getroot()
            return root.find("ce")
        except Exception as ex:
            logger.warning("Could not get CE element from %s: %s", ce_path, ex)
            return None

    def get_ce_folder(self, ce_path: str) -> str | None:
        ce = self.get_ce_element(ce_path)
        if ce is not None:
            result = ce.get("folder")
            assert result is None or isinstance(result, str)
            return result
        return None

    def get_types_dir(self, ce_path: str) -> str | None:
        folder = self.get_ce_folder(ce_path)
        config_dir = os.path.dirname(ce_path)
        if folder:
            return os.path.join(config_dir, folder)
        return config_dir

    def create_type_file(self, ce_path: str, filename: str) -> str | None:
        logger.info("Creating type file: %s in config %s", filename, ce_path)
        if not filename.endswith(".xml"):
            filename += ".xml"

        types_dir = self.get_types_dir(ce_path)
        if not types_dir:
            logger.error("Could not determine types directory for %s", ce_path)
            return None

        file_path = os.path.join(types_dir, filename)

        if not os.path.exists(file_path):
            try:
                os.makedirs(types_dir, exist_ok=True)
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(TYPES_TEMPLATE)
                logger.debug("Created file: %s", file_path)
            except Exception as ex:
                logger.error("Failed to create file %s: %s", file_path, ex)
                return None

        try:
            tree = ET.parse(ce_path)
            root = tree.getroot()
            ce = root.find("ce")

            if ce is None:
                ce = ET.SubElement(root, "ce")
                ce.set("folder", "db")

            already_in_config = any(
                fe.get("name") == filename for fe in ce.findall("file")
            )

            if not already_in_config:
                file_elem = ET.SubElement(ce, "file")
                file_elem.set("name", filename)
                file_elem.set("type", "types")
                ET.indent(tree, space="\t")
                tree.write(ce_path, encoding="UTF-8", xml_declaration=True)
                logger.debug("Registered %s in config", filename)

            return file_path
        except Exception as ex:
            logger.error("Failed to register %s in config: %s", filename, ex)
            return None

    def delete_type_file(self, ce_path: str, filename: str) -> bool:
        logger.info("Deleting type file: %s from config %s", filename, ce_path)
        types_dir = self.get_types_dir(ce_path)
        if not types_dir:
            return False

        file_path = os.path.join(types_dir, filename)
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
                logger.debug("Deleted file: %s", file_path)
        except Exception as ex:
            logger.error("Failed to delete file %s: %s", file_path, ex)
            return False

        try:
            tree = ET.parse(ce_path)
            self.remove_file_from_ce(tree, filename)
            ET.indent(tree, space="\t")
            tree.write(ce_path, encoding="UTF-8", xml_declaration=True)
            logger.debug("Unregistered %s from config", filename)
            return True
        except Exception as ex:
            logger.error("Failed to update config after deleting %s: %s", filename, ex)
            return False

    def add_file_to_ce(self, tree: ET.ElementTree, filename: str) -> bool:
        root = tree.getroot()
        ce = root.find("ce")
        if ce is None:
            ce = ET.SubElement(root, "ce")
            ce.set("folder", "db")
        already = any(fe.get("name") == filename for fe in ce.findall("file"))
        if not already:
            fe = ET.SubElement(ce, "file")
            fe.set("name", filename)
            fe.set("type", "types")
            logger.debug("Added %s to CE", filename)
            return True
        logger.debug("%s already in CE", filename)
        return False

    def remove_file_from_ce(self, tree: ET.ElementTree, filename: str) -> bool:
        root = tree.getroot()
        ce = root.find("ce")
        if ce is not None:
            for fe in ce.findall("file"):
                if fe.get("name") == filename:
                    ce.remove(fe)
                    if len(ce.findall("file")) == 0 and not ce.get("folder"):
                        root.remove(ce)
                    logger.debug("Removed %s from CE", filename)
                    return True
        logger.debug("%s not found in CE", filename)
        return False
