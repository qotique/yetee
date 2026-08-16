from __future__ import annotations

import json
import logging

from lxml import etree as ET

from exceptions import ParseError, AccessError
from models.field_def import FieldDef, FieldType
from models.row_data import RowData

logger = logging.getLogger(__name__)


def _text(elem: ET.Element, key: str) -> str:
    value = elem.get(key)
    if value is not None:
        return str(value)
    for child in elem:
        if child.tag == key and len(child) == 0:
            return (child.text or "").strip()
    return ""


def _set_text(elem: ET.Element, key: str, value: str) -> None:
    if elem.get(key) is not None:
        elem.set(key, value)
        return
    for child in elem:
        if child.tag == key and len(child) == 0:
            child.text = value
            return
    elem.set(key, value)


def _collect_keys(elems: list[ET.Element]) -> list[str]:
    keys: list[str] = []
    for elem in elems:
        for attr in elem.keys():
            if attr not in keys:
                keys.append(attr)
        for child in elem:
            if not isinstance(child.tag, str):
                continue
            if len(child) == 0 and child.tag not in keys:
                keys.append(child.tag)
    return sorted(keys)


def _stringify(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        return value
    return json.dumps(value)


def _value_type(value: object) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "float"
    if isinstance(value, (dict, list)):
        return "json"
    return "str"


def _coerce(value_type: str, text: str) -> object:
    stripped = text.strip()
    if value_type in ("null",):
        return None if stripped == "" else text
    if value_type == "bool":
        return tweaked_bool(stripped)
    if value_type == "int":
        return _parse_int(stripped)
    if value_type == "float":
        return _parse_float(stripped)
    if value_type == "json":
        if stripped == "":
            return None
        try:
            return json.loads(stripped)
        except ValueError:
            return text
    return text


def tweaked_bool(text: str) -> bool:
    return text.lower() in ("1", "true", "yes", "on")


def _parse_int(text: str) -> int | None:
    if text == "":
        return None
    try:
        return int(text)
    except ValueError:
        return None


def _parse_float(text: str) -> float | None:
    if text == "":
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _coerce_field_type(fd: FieldDef, text: str, native: str) -> object:
    if fd.is_bool():
        return tweaked_bool(text.strip())
    if fd.is_toggle():
        stripped = text.strip()
        return 1 if stripped in ("1", "true", "yes", "on") else 0 if stripped else None
    if fd.is_int():
        return _parse_int(text.strip())
    if fd.is_float():
        return _parse_float(text.strip())
    return _coerce(native, text)


def _flatten(node: object, prefix: str, depth: int) -> list[tuple[str, object]]:
    if depth > 24:
        key = prefix.lstrip(".") if prefix else "value"
        return [(key, node)]
    if isinstance(node, dict):
        flat: list[tuple[str, object]] = []
        for key, value in node.items():
            sub = f"{prefix}.{key}" if prefix else str(key)
            flat.extend(_flatten(value, sub, depth + 1))
        return flat
    if isinstance(node, list):
        flat2: list[tuple[str, object]] = []
        for idx, value in enumerate(node):
            sub = f"{prefix}.{idx}" if prefix else str(idx)
            flat2.extend(_flatten(value, sub, depth + 1))
        return flat2
    return [(prefix, node)]


def _set_leaf(out: dict[str, object], path: str, value: object) -> None:
    if not path:
        out["value"] = value
        return
    keys = path.split(".")
    node = out
    for key in keys[:-1]:
        current = node.setdefault(key, {})
        if not isinstance(current, dict):
            current = {}
            node[key] = current
        node = current
    node[keys[-1]] = value


class XmlSettingsRepository:
    """Generic settings-table repository over arbitrary XML.

    Records are the repeated non-leaf children of the root; when the root has
    no repeated element it is treated as a single record. Columns are the
    union of record attributes and leaf-child tags. Save writes scalar values
    back into the cached tree, preserving unrelated structure.
    """

    def __init__(self) -> None:
        self._trees: dict[str, ET._ElementTree] = {}
        self._records: dict[str, list[ET.Element]] = {}

    def parse_file(
        self,
        path: str,
        schema: tuple[FieldDef, ...] | None = None,
    ) -> tuple[list[FieldDef], list[RowData]]:
        try:
            tree = ET.parse(path)
        except ET.ParseError as ex:
            raise ParseError(f"Failed to parse {path}: {ex}") from ex
        except FileNotFoundError as ex:
            raise AccessError(f"File not found: {path}") from ex
        except Exception as ex:
            logger.exception("Failed to read %s", path)
            raise AccessError(f"Cannot read {path}: {ex}") from ex

        self._trees[path] = tree
        root = tree.getroot()

        records = self._find_records(root)
        if records:
            keys = _collect_keys(records)
            rows = [
                RowData(values={key: _text(e, key) for key in keys}, flags={}, elem=e)
                for e in records
            ]
        else:
            keys = _collect_keys([root])
            rows = [
                RowData(values={key: _text(root, key) for key in keys}, flags={}, elem=root)
            ]

        self._records[path] = records or [root]
        field_defs = [
            FieldDef(key=key, label=key, type=FieldType.TEXT, width=150)
            for key in keys
        ]
        logger.debug("Parsed %d settings rows from %s", len(rows), path)
        return field_defs, rows

    def _find_records(self, root: ET.Element) -> list[ET.Element]:
        children = [c for c in root if isinstance(c.tag, str)]
        if not children:
            return []
        counts: dict[str, int] = {}
        for child in children:
            tag = child.tag
            assert isinstance(tag, str)
            counts[tag] = counts.get(tag, 0) + 1
        best_tag = max(counts, key=lambda tag: counts[tag])
        assert isinstance(best_tag, str)
        if counts[best_tag] <= 1:
            return []
        return [c for c in root if c.tag == best_tag]

    def save(self, path: str, rows: list[RowData]) -> None:
        tree = self._trees.get(path)
        if tree is None:
            raise ParseError(f"No element tree available for {path}")
        for row in rows:
            elem = row.elem
            if elem is None:
                continue
            for key, value in row.values.items():
                _set_text(elem, key, value)
        try:
            root = tree.getroot()
            ET.indent(root, space="\t")
            tree.write(path, encoding="UTF-8", xml_declaration=True)
            logger.info("Saved %s successfully", path)
        except Exception as ex:
            logger.error("Failed to save %s: %s", path, ex)
            raise AccessError(f"Failed to save {path}: {ex}") from ex

    def invalidate_cache(self, path: str) -> None:
        self._trees.pop(path, None)
        self._records.pop(path, None)


class JsonSettingsRepository:
    """Generic settings-table over a JSON document.

    Two native shapes are supported:
    - JSON object / list of scalars -> rows of ``path`` (dot-notation) and
      ``value`` columns,
    - JSON array of objects -> one row per object with the union of their
      keys as columns.
    Save reconstructs the document from the edited rows and type metadata
    captured at parse time.
    """

    def __init__(self) -> None:
        self._docs: dict[str, object] = {}
        self._object_types: dict[str, dict[str, str]] = {}
        self._array_types: dict[str, list[dict[str, str]]] = {}
        self._flat_schema: dict[str, tuple[dict[str, FieldDef], dict[str, str]]] = {}

    def parse_file(
        self,
        path: str,
        schema: tuple[FieldDef, ...] | None = None,
    ) -> tuple[list[FieldDef], list[RowData]]:
        try:
            with open(path, encoding="utf-8") as fh:
                doc = json.load(fh)
        except OSError as ex:
            raise AccessError(f"Cannot read {path}: {ex}") from ex
        except json.JSONDecodeError as ex:
            raise ParseError(f"Failed to parse JSON {path}: {ex}") from ex

        self._docs[path] = doc
        return self._rows_for(doc, path, schema)

    def load_doc(self, path: str) -> object:
        if path in self._docs:
            return self._docs[path]
        try:
            with open(path, encoding="utf-8") as fh:
                doc = json.load(fh)
        except OSError as ex:
            raise AccessError(f"Cannot read {path}: {ex}") from ex
        except json.JSONDecodeError as ex:
            raise ParseError(f"Failed to parse JSON {path}: {ex}") from ex
        self._docs[path] = doc
        return doc

    def save_doc(self, path: str, doc: object) -> None:
        try:
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(doc, fh, ensure_ascii=False, indent=2)
            logger.info("Saved %s successfully", path)
        except Exception as ex:
            logger.error("Failed to save %s: %s", path, ex)
            raise AccessError(f"Failed to save {path}: {ex}") from ex
        self._docs[path] = doc

    def _rows_for(
        self,
        doc: object,
        path: str,
        schema: tuple[FieldDef, ...] | None = None,
    ) -> tuple[list[FieldDef], list[RowData]]:
        if isinstance(doc, dict) and schema:
            return self._rows_for_flat_schema(doc, path, schema)
        if isinstance(doc, list) and all(isinstance(o, dict) for o in doc):
            return self._rows_for_array(doc, path)
        return self._rows_for_object(doc, path)

    def _rows_for_flat_schema(
        self,
        doc: dict[str, object],
        path: str,
        schema: tuple[FieldDef, ...],
    ) -> tuple[list[FieldDef], list[RowData]]:
        declared: dict[str, FieldDef] = {}
        for fd in schema:
            if fd.key in doc:
                declared[fd.key] = fd
        extra = [key for key in doc if key not in declared]

        field_defs: list[FieldDef] = []
        for fd in schema:
            if fd.key in declared:
                field_defs.append(fd)
        for key in extra:
            field_defs.append(
                FieldDef(key=key, label=key, type=FieldType.TEXT, width=160)
            )

        values: dict[str, str] = {}
        native: dict[str, str] = {}
        for key in list(declared) + extra:
            value = doc[key]
            values[key] = _stringify(value)
            native[key] = _value_type(value)
        rows = [RowData(values=values, flags={}, elem=None)]

        self._flat_schema[path] = (declared, native)
        self._object_types.pop(path, None)
        self._array_types.pop(path, None)
        return field_defs, rows

    def _rows_for_object(
        self, doc: object, path: str
    ) -> tuple[list[FieldDef], list[RowData]]:
        fields = [
            FieldDef("path", "Path", FieldType.TEXT, width=300),
            FieldDef("value", "Value", FieldType.TEXT, width=300),
        ]
        keys: dict[str, str] = {}
        rows: list[RowData] = []
        for key, value in _flatten(doc, "", 0):
            k = key.lstrip(".")
            keys[k] = _value_type(value)
            rows.append(
                RowData(
                    values={"path": k, "value": _stringify(value)},
                    flags={},
                    elem=None,
                )
            )
        self._object_types[path] = keys
        self._array_types.pop(path, None)
        self._flat_schema.pop(path, None)
        return fields, rows

    def _rows_for_array(
        self, doc: list[dict[str, object]], path: str
    ) -> tuple[list[FieldDef], list[RowData]]:
        keys: list[str] = []
        for obj in doc:
            for key in obj.keys():
                if key not in keys:
                    keys.append(key)
        fields = [
            FieldDef(key=key, label=key, type=FieldType.TEXT, width=160)
            for key in keys
        ]
        rows: list[RowData] = []
        per_row: list[dict[str, str]] = []
        for obj in doc:
            values: dict[str, str] = {}
            types: dict[str, str] = {}
            for key in keys:
                v = obj.get(key)
                values[key] = _stringify(v)
                types[key] = _value_type(v)
            rows.append(RowData(values=values, flags={}, elem=None))
            per_row.append(types)
        self._array_types[path] = per_row
        self._object_types.pop(path, None)
        self._flat_schema.pop(path, None)
        return fields, rows

    def save(self, path: str, rows: list[RowData]) -> None:
        if self._docs.get(path) is None:
            raise ParseError(f"No document loaded for {path}")
        if path in self._flat_schema:
            declared, native = self._flat_schema[path]
            values: object = self._build_flat(rows, declared, native)
        elif path in self._array_types:
            values = self._build_array(rows, self._array_types[path])
        else:
            values = self._build_object(rows, self._object_types.get(path, {}))
        try:
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(values, fh, ensure_ascii=False, indent=2)
            logger.info("Saved %s successfully", path)
        except Exception as ex:
            logger.error("Failed to save %s: %s", path, ex)
            raise AccessError(f"Failed to save {path}: {ex}") from ex

    def _build_object(
        self, rows: list[RowData], key_types: dict[str, str]
    ) -> dict[str, object]:
        out: dict[str, object] = {}
        for row in rows:
            path = row.values.get("path", "")
            text = row.values.get("value", "")
            _set_leaf(out, path, _coerce(key_types.get(path, "str"), text))
        return out

    def _build_flat(
        self,
        rows: list[RowData],
        declared: dict[str, FieldDef],
        native: dict[str, str],
    ) -> dict[str, object]:
        out: dict[str, object] = {}
        if not rows:
            return out
        for key, text in rows[0].values.items():
            fd = declared.get(key)
            out[key] = (
                _coerce_field_type(fd, text, native.get(key, "str"))
                if fd
                else _coerce(native.get(key, "str"), text)
            )
        return out

    def _build_array(
        self, rows: list[RowData], row_types: list[dict[str, str]]
    ) -> list[object]:
        out: list[object] = []
        for idx, row in enumerate(rows):
            obj: dict[str, object] = {}
            types_for = row_types[idx] if idx < len(row_types) else {}
            for key, text in row.values.items():
                obj[key] = _coerce(types_for.get(key, "str"), text)
            out.append(obj)
        return out

    def invalidate_cache(self, path: str) -> None:
        self._docs.pop(path, None)
        self._object_types.pop(path, None)
        self._array_types.pop(path, None)
        self._flat_schema.pop(path, None)