from __future__ import annotations

import re
from dataclasses import dataclass

from models.field_def import FieldType


@dataclass(frozen=True)
class FormField:
    """One typed field of a form (scalar value)."""

    key: str
    label: str
    type: FieldType = FieldType.TEXT
    options: tuple[str, ...] = ()


@dataclass(frozen=True)
class FormGrid:
    """Nested list-of-objects rendered as an editable grid (one row per item).

    When ``item_schema`` is set, each item is rendered as a recursive sub-form
    (used for nested objects that themselves contain lists/dicts, e.g. loadout
    inventory slots). Otherwise ``columns`` describe a flat table.
    """

    key: str
    label: str
    columns: tuple[FormField, ...] = ()
    item_schema: "FormSchema | None" = None


@dataclass(frozen=True)
class FormList:
    """Nested list of scalar values (strings, numbers, toggles)."""

    key: str
    label: str
    item_type: FieldType = FieldType.TEXT


@dataclass(frozen=True)
class FormDict:
    """Nested mapping of scalar keys to scalar values (e.g. trader Items)."""

    key: str
    label: str
    value_type: FieldType = FieldType.TEXT


@dataclass(frozen=True)
class FormGroup:
    """Nested object rendered as a recursive sub-form."""

    key: str
    label: str
    schema: "FormSchema"


@dataclass(frozen=True)
class FormSchema:
    """The full form description of one file.

    ``name_key`` selects the field that labels a master-list entry when the
    underlying document is an array of objects (e.g. ``DisplayName``).
    """

    fields: tuple[FormField, ...] = ()
    grids: tuple[FormGrid, ...] = ()
    lists: tuple[FormList, ...] = ()
    dicts: tuple[FormDict, ...] = ()
    groups: tuple[FormGroup, ...] = ()
    name_key: str | None = None


_FORM_SCHEMAS: dict[tuple[str, str], FormSchema] = {}
_FORM_FOLDER_SCHEMAS: dict[tuple[str, str], FormSchema] = {}


def register_form_schema(
    entity: str, filename: str, schema: FormSchema
) -> None:
    _FORM_SCHEMAS[(entity, filename)] = schema


def register_form_folder_schema(
    entity: str, folder: str, schema: FormSchema
) -> None:
    _FORM_FOLDER_SCHEMAS[(entity, folder.rstrip("/"))] = schema


def get_form_schema(entity: str, filename: str) -> FormSchema | None:
    return _FORM_SCHEMAS.get((entity, filename))


def has_form_schema(entity: str, filename: str) -> bool:
    return (entity, filename) in _FORM_SCHEMAS


def get_form_schema_for_path(entity: str, path: str) -> FormSchema | None:
    filename = path.rsplit("/", 1)[-1]
    direct = _FORM_SCHEMAS.get((entity, filename))
    if direct is not None:
        return direct
    norm = f"/{path.replace('\\\\', '/').strip('/')}/"
    for (ent, folder), schema in _FORM_FOLDER_SCHEMAS.items():
        if ent == entity and f"/{folder}/" in norm:
            return schema
    return None


def entity_has_form_schemas(entity: str, files: dict[str, str]) -> bool:
    return any(get_form_schema_for_path(entity, path) is not None for path in files.values())


_CAMEL_RE = re.compile(r"([a-z0-9])([A-Z])")


def humanize_key(key: str) -> str:
    """Convert a JSON key to a readable label.

    ``ServerUpdateRateLimit`` -> ``Server Update Rate Limit``,
    ``#STR_EXPANSION_MARKET_CATEGORY_FOOD`` -> ``Expansion Market Category Food``,
    ``m_Version`` -> ``Version``.
    """
    text = key
    if text.startswith("#STR_"):
        text = text[len("#STR_") :]
    if text.startswith("m_"):
        text = text[2:]
    text = text.replace("_", " ")
    text = _CAMEL_RE.sub(r"\1 \2", text)
    words = [w.capitalize() for w in text.split() if w]
    return " ".join(words) if words else key


def _type_from_values(values: list[object]) -> FieldType:
    present = [v for v in values if v is not None]
    if not present:
        return FieldType.TEXT
    if all(isinstance(v, bool) for v in present):
        return FieldType.BOOL
    if all(isinstance(v, int) and not isinstance(v, bool) for v in present):
        if all(v in (0, 1) for v in present):
            return FieldType.TOGGLE
        return FieldType.INT
    if all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in present):
        return FieldType.FLOAT
    return FieldType.TEXT


def _field_from_value(key: str, value: object) -> FormField:
    ftype = _type_from_values([value])
    return FormField(key=key, label=humanize_key(key), type=ftype)


def _columns_from_items(items: list[dict[str, object]]) -> tuple[FormField, ...]:
    keys: list[str] = []
    for obj in items:
        for key in obj:
            if key not in keys:
                keys.append(key)
    columns: list[FormField] = []
    for key in keys:
        values = [obj.get(key) for obj in items if key in obj]
        columns.append(FormField(key=key, label=humanize_key(key), type=_type_from_values(values)))
    return tuple(columns)


def _item_type_from_list(values: list[object]) -> FieldType:
    scalars = [v for v in values if not isinstance(v, (dict, list))]
    return _type_from_values(scalars) if scalars else FieldType.TEXT


def _schema_for_object(obj: dict[str, object], *, with_name_key: bool) -> FormSchema:
    fields: list[FormField] = []
    grids: list[FormGrid] = []
    lists: list[FormList] = []
    dicts: list[FormDict] = []
    groups: list[FormGroup] = []

    for key, value in obj.items():
        if isinstance(value, dict):
            if value and all(
                not isinstance(v, (dict, list)) for v in value.values()
            ):
                dicts.append(
                    FormDict(
                        key=key,
                        label=humanize_key(key),
                        value_type=_type_from_values(list(value.values())),
                    )
                )
            else:
                groups.append(
                    FormGroup(
                        key=key,
                        label=humanize_key(key),
                        schema=_schema_for_object(value, with_name_key=False),
                    )
                )
        elif isinstance(value, list):
            if value and all(isinstance(o, dict) for o in value):
                items = [o for o in value if isinstance(o, dict)]
                nested = any(
                    isinstance(v, (dict, list))
                    for o in items
                    for v in o.values()
                )
                if nested:
                    grids.append(
                        FormGrid(
                            key=key,
                            label=humanize_key(key),
                            item_schema=_schema_for_object(
                                items[0], with_name_key=True
                            ),
                        )
                    )
                else:
                    grids.append(
                        FormGrid(
                            key=key,
                            label=humanize_key(key),
                            columns=_columns_from_items(items),
                        )
                    )
            else:
                lists.append(
                    FormList(
                        key=key,
                        label=humanize_key(key),
                        item_type=_item_type_from_list(value),
                    )
                )
        else:
            fields.append(_field_from_value(key, value))

    name_key: str | None = None
    if with_name_key:
        for candidate in ("DisplayName", "ClassName", "Filename", "Name", "Title"):
            if candidate in obj:
                name_key = candidate
                break

    return FormSchema(
        fields=tuple(fields),
        grids=tuple(grids),
        lists=tuple(lists),
        dicts=tuple(dicts),
        groups=tuple(groups),
        name_key=name_key,
    )


def build_auto_form_schema(doc: object) -> FormSchema:
    """Derive a ``FormSchema`` from the native JSON structure.

    Flat dict values become typed fields (bool->BOOL, 0/1-int->TOGGLE,
    int->INT, float->FLOAT, str->TEXT). Nested dicts become ``FormGroup``,
    arrays of objects become ``FormGrid``, arrays of scalars become
    ``FormList``. All labels are humanized.
    """
    if isinstance(doc, list):
        items = [o for o in doc if isinstance(o, dict)]
        if items:
            return _schema_for_object(items[0], with_name_key=True)
        return FormSchema()
    if isinstance(doc, dict):
        return _schema_for_object(doc, with_name_key=False)
    return FormSchema()
