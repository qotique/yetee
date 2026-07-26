from __future__ import annotations

import os
from lxml import etree as ET

import flet as ft


TYPES_TEMPLATE = """<?xml version="1.0" encoding="UTF-8" standalone="yes" ?>
<types>
</types>
"""


class ConfigService:
    def __init__(self, page: ft.Page):
        self._page = page

    def load_files(self, ce_path: str) -> list[str]:
        files: list[str] = []
        tree = ET.parse(ce_path)
        root = tree.getroot()
        ce = root.find("ce")
        if ce is not None:
            for file_elem in ce.findall("file"):
                name = file_elem.get("name", "")
                if name:
                    files.append(name)
        return files

    def get_ce_element(self, ce_path: str) -> ET.Element | None:
        tree = ET.parse(ce_path)
        root = tree.getroot()
        return root.find("ce")

    def get_ce_folder(self, ce_path: str) -> str | None:
        ce = self.get_ce_element(ce_path)
        if ce is not None:
            return ce.get("folder")
        return None

    def get_types_dir(self, ce_path: str) -> str | None:
        folder = self.get_ce_folder(ce_path)
        config_dir = os.path.dirname(ce_path)
        if folder:
            return os.path.join(config_dir, folder)
        return config_dir

    def create_type_file(self, ce_path: str, filename: str) -> str | None:
        if not filename.endswith(".xml"):
            filename += ".xml"

        types_dir = self.get_types_dir(ce_path)
        if not types_dir:
            return None

        file_path = os.path.join(types_dir, filename)

        if not os.path.exists(file_path):
            try:
                os.makedirs(types_dir, exist_ok=True)
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(TYPES_TEMPLATE)
            except Exception:
                return None

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

        return file_path

    def delete_type_file(self, ce_path: str, filename: str) -> bool:
        types_dir = self.get_types_dir(ce_path)
        if not types_dir:
            return False

        file_path = os.path.join(types_dir, filename)
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
        except Exception:
            return False

        tree = ET.parse(ce_path)
        self.remove_file_from_ce(tree, filename)
        ET.indent(tree, space="\t")
        tree.write(ce_path, encoding="UTF-8", xml_declaration=True)
        return True

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
            return True
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
                    return True
        return False
