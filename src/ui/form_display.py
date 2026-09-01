from __future__ import annotations

import logging
import os
from collections.abc import Callable

import flet as ft

from commands.registry import CommandRegistry
from core.exceptions import AccessError, ParseError
from models.form_schema import (
    FormDict,
    FormField,
    FormGrid,
    FormGroup,
    FormList,
    FormSchema,
    build_auto_form_schema,
    get_form_schema_for_path,
)
from models.field_def import FieldType
from repository.settings_repository import JsonSettingsRepository

logger = logging.getLogger(__name__)


CREATE_CATEGORIES: frozenset[str] = frozenset(
    {
        "AI/LootDrops",
        "Loadouts",
        "Quests/NPCs",
        "Quests/Objectives",
        "Quests/Quests",
        "Traders",
        "Market",
    }
)


def _human_coerce(ftype: FieldType, value: object) -> object:
    if isinstance(value, str):
        text = value.strip()
        if ftype in (FieldType.INT, FieldType.TOGGLE):
            try:
                return int(text) if text else None
            except ValueError:
                return value
        if ftype == FieldType.FLOAT:
            try:
                return float(text) if text else None
            except ValueError:
                return value
        if ftype == FieldType.BOOL:
            return text.lower() in ("1", "true", "yes", "on")
    return value


def _scalar_widget_value(ftype: FieldType, value: object) -> str:
    if value is None:
        return ""
    if ftype in (FieldType.TEXT, FieldType.INT, FieldType.FLOAT):
        return str(value)
    return str(value)


class FormDisplay:
    """Master-detail form editor for custom entities.

    Loads a JSON document through ``JsonSettingsRepository.load_doc``, resolves
    a ``FormSchema`` (declared in ``models/form_schema.py``/``models/expansion.py`` or built
    automatically from the JSON structure) and renders a typed form on the
    right. When the entity has several files (or a single array-of-objects
    file) a master list on the left selects the current document / item.

    Satisfies the same public surface as ``SettingsTableDisplay`` so it can be
    used as an ``_EntityConfig.display``. Save rebuilds the document from live
    controls (recursively) and writes it back via ``JsonSettingsRepository.
    save_doc``.
    """

    def __init__(
        self,
        page: ft.Page,
        json_repo: JsonSettingsRepository | None = None,
        commands: CommandRegistry | None = None,
    ):
        self._page = page
        self._json_repo = json_repo or JsonSettingsRepository()
        self._commands = commands

        self.on_saved: Callable[[], None] | None = None
        self.on_file_select: Callable[[str], None] | None = None
        self.on_file_create: Callable[[str, str], None] | None = None

        self._entity: str = ""
        self._files: dict[str, str] = {}
        self._path: str | None = None
        self._filename: str = ""
        self._doc: object = None
        self._schema: FormSchema = FormSchema()
        self._dirty: bool = False
        self._master_mode: str = "none"  # "files" | "items" | "none"
        self._selected_item: int = 0
        self._current_label: str = ""
        self._master_seed: tuple[object, ...] | None = None
        self._master_rows: dict[str, ft.Container] = {}
        self._master_tiles: dict[tuple[str, ...], ft.ExpansionTile] = {}
        self._master_item_rows: dict[int, ft.Container] = {}

        self._master = ft.Column(scroll=ft.ScrollMode.AUTO, expand=True, spacing=0)
        self._detail = ft.Column(scroll=ft.ScrollMode.AUTO, expand=True, spacing=4)
        self._master_container = ft.Container(
            width=280, content=self._master, visible=False
        )
        self._divider = ft.VerticalDivider(visible=False)
        self._detail_container = ft.Container(expand=True, content=self._detail)
        self._core = ft.Row(
            [
                self._master_container,
                self._divider,
                self._detail_container,
            ],
            expand=True,
            spacing=0,
        )
        self.control = ft.Container(visible=False, expand=True, content=self._core)

        self._status = ft.Text("", size=12, selectable=True)
        self._save_btn = ft.Button(
            "Save",
            icon=ft.Icons.SAVE,
            on_click=self._bind("save", self.save_current),
        )
        self.button_row = ft.Row(
            [self._save_btn, ft.Divider(), self._status],
            alignment=ft.MainAxisAlignment.START,
        )

    def _bind(
        self,
        command_id: str,
        fallback: Callable[[object], None],
    ) -> Callable[[object], None]:
        commands = self._commands
        if commands is not None:
            return lambda _e: commands.invoke(command_id)
        return fallback

    # ------------------------------------------------------------------ public

    def set_entity(self, entity: str) -> None:
        self._entity = entity

    def set_files(self, files: dict[str, str]) -> None:
        self._files = dict(files)

    @property
    def is_dirty(self) -> bool:
        return self._dirty

    def _set_status(self, message: str) -> None:
        self._status.value = message
        self._status.update()

    def load_file(self, path: str) -> None:
        self._load_file_impl(path)

    async def load_file_async(
        self,
        path: str,
        cancel_check: Callable[[], bool] | None = None,
    ) -> None:
        try:
            self._load_file_impl(path)
        except (ParseError, AccessError) as ex:
            logger.warning("Form load failed for %s: %s", path, ex)
            self._set_status(f"Error loading: {ex}")

    async def preload_cached(
        self,
        paths: list[str],
        on_progress: Callable[[int, int], None] | None = None,
        cancel_check: Callable[[], bool] | None = None,
    ) -> None:
        for done in range(1, len(paths) + 1):
            if cancel_check and cancel_check():
                return
            if on_progress:
                on_progress(done, len(paths))

    def save_current(self, e: object = None) -> None:
        self._save_current_file()

    def save_file(self) -> None:
        self._save_current_file()

    def save_async(self) -> None:
        self._save_current_file()

    def clear(self) -> None:
        self._entity = ""
        self._files = {}
        self._path = None
        self._filename = ""
        self._doc = None
        self._schema = FormSchema()
        self._dirty = False
        self._master_mode = "none"
        self._selected_item = 0
        self._current_label = ""
        self._master_seed = None
        self._master_rows = {}
        self._master_tiles = {}
        self._master_item_rows = {}
        self._master.controls = []
        self._detail.controls = []
        self._master_container.visible = False
        self._divider.visible = False
        self.control.visible = False

    def clear_cache(self, path: str) -> None:
        self._json_repo.invalidate_cache(path)

    # ------------------------------------------------------------------ load

    def _load_file_impl(self, path: str) -> None:
        self._path = path
        self._filename = path.rsplit("/", 1)[-1]
        doc = self._json_repo.load_doc(path)
        declared = get_form_schema_for_path(self._entity, path)
        self._schema = declared or build_auto_form_schema(doc)
        self._doc = doc
        self._dirty = False
        self._selected_item = 0
        previous_label = self._current_label
        self._current_label = self._label_for_path(path)
        seed = self._master_files_seed()
        seed_changed = seed != self._master_seed
        if seed_changed:
            self._master_seed = seed
            self._rebuild_master()
        else:
            self._refresh_master_selection(previous_label, self._current_label)
        self._render_detail()
        self.control.visible = True
        self._set_status("")
        try:
            if seed_changed:
                self.control.update()
            else:
                self._detail.update()
        except RuntimeError:
            pass

    def _master_files_seed(self) -> tuple[object, ...]:
        return (self._entity, sorted(self._files.items()))

    def _refresh_master_selection(self, old_label: str, new_label: str) -> None:
        if self._master_mode == "items":
            if isinstance(self._doc, list):
                self._build_item_master(self._doc)
            return
        if self._master_mode != "files":
            return
        old_row = self._master_rows.get(old_label)
        new_row = self._master_rows.get(new_label)
        if old_row is not None and old_label != new_label:
            self._restyle_master_row(old_row, False)
            self._update_master_row(old_row)
        if new_row is not None and new_label != old_label:
            self._restyle_master_row(new_row, True)
            self._update_master_row(new_row)
        for path, tile in self._master_tiles.items():
            expanded = self._path_expanded(path)
            if tile.expanded != expanded:
                tile.expanded = expanded
                self._update_master_row(tile)

    def _restyle_master_row(self, row: ft.Container, selected: bool) -> None:
        row.bgcolor = ft.Colors.SECONDARY_CONTAINER if selected else None
        row.border = ft.Border(
            left=ft.BorderSide(
                width=3,
                color=ft.Colors.PRIMARY if selected else ft.Colors.TRANSPARENT,
            )
        )
        text = row.content
        if isinstance(text, ft.Text):
            text.weight = ft.FontWeight.W_600 if selected else ft.FontWeight.NORMAL
            text.color = ft.Colors.PRIMARY if selected else None

    def _update_master_row(self, row: ft.Control) -> None:
        try:
            row.update()
        except RuntimeError:
            pass

    def _label_for_path(self, path: str) -> str:
        for label, candidate in self._files.items():
            if candidate == path:
                return label
        return self._filename

    def _doc_for_detail(self) -> object:
        if self._master_mode == "items" and isinstance(self._doc, list):
            items = self._doc
            if items and 0 <= self._selected_item < len(items):
                return items[self._selected_item]
        return self._doc

    # ----------------------------------------------------------------- master

    def _rebuild_master(self) -> None:
        if len(self._files) > 1:
            self._master_mode = "files"
            self._build_file_master()
        elif isinstance(self._doc, list) and all(
            isinstance(o, dict) for o in self._doc
        ):
            self._master_mode = "items"
            self._build_item_master(self._doc)
        else:
            self._master_mode = "none"
            self._master.controls = []
        self._master_container.visible = self._master_mode != "none"
        self._divider.visible = self._master_container.visible

    def _build_file_master(self) -> None:
        self._master_rows = {}
        self._master_tiles = {}
        self._master.controls = self._render_file_tree(self._build_file_tree())

    def _build_file_tree(self) -> dict[str, object]:
        tree: dict[str, object] = {}
        for label in self._files:
            parts = label.split("/")
            node = tree
            for part in parts[:-1]:
                child = node.get(part)
                if not isinstance(child, dict):
                    child = {}
                    node[part] = child
                node = child
            node[parts[-1]] = label
        return tree

    def _render_file_tree(
        self, tree: dict[str, object], path: tuple[str, ...] = ()
    ) -> list[ft.Control]:
        rows: list[ft.Control] = []
        for key in sorted(tree.keys()):
            value = tree[key]
            if isinstance(value, dict):
                child_path = path + (key,)
                controls = self._render_file_tree(value, child_path)
                if self._can_create_in(child_path):
                    controls.append(self._create_category_row(child_path))
                tile = ft.ExpansionTile(
                    title=ft.Text(
                        key,
                        size=12,
                        weight=ft.FontWeight.BOLD,
                        color=ft.Colors.ON_SURFACE_VARIANT,
                    ),
                    controls=controls,
                    dense=True,
                    expanded=self._path_expanded(child_path),
                )
                self._master_tiles[child_path] = tile
                rows.append(tile)
            else:
                label = value
                assert isinstance(label, str)
                display = label.rsplit("/", 1)[-1]
                selected = label == self._current_label
                row = self._master_row(
                    display,
                    selected,
                    on_click=self._on_file_master_click,
                    data=label,
                )
                self._master_rows[label] = row
                rows.append(row)
        return rows

    def _path_expanded(self, path: tuple[str, ...]) -> bool:
        parts = self._current_label.split("/")
        return len(path) <= len(parts) and list(path) == parts[: len(path)]

    def _build_item_master(self, items: list[object]) -> None:
        rows: list[ft.Control] = []
        self._master_item_rows = {}
        for idx, item in enumerate(items):
            label = self._item_label(item, idx)
            selected = idx == self._selected_item
            row = self._master_row(
                label, selected, on_click=self._on_item_master_click, idx=idx
            )
            self._master_item_rows[idx] = row
            rows.append(row)
        self._master.controls = rows

    def _item_label(self, item: object, idx: int) -> str:
        if isinstance(item, dict):
            if self._schema.name_key and self._schema.name_key in item:
                return str(item[self._schema.name_key])
            if item:
                first_key = next(iter(item))
                return f"{first_key}: {item[first_key]}"
        return f"Item {idx + 1}"

    def _master_row(
        self,
        label: str,
        selected: bool,
        on_click: Callable[[ft.ControlEvent], None],
        idx: int | None = None,
        data: str | None = None,
    ) -> ft.Container:
        return ft.Container(
            content=ft.Text(
                label,
                size=13,
                no_wrap=True,
                overflow=ft.TextOverflow.ELLIPSIS,
                weight=ft.FontWeight.W_600 if selected else ft.FontWeight.NORMAL,
                color=ft.Colors.PRIMARY if selected else None,
            ),
            padding=ft.Padding(left=12, right=12, top=8, bottom=8),
            bgcolor=ft.Colors.SECONDARY_CONTAINER if selected else None,
            border=ft.Border(
                left=ft.BorderSide(
                    width=3,
                    color=ft.Colors.PRIMARY if selected else ft.Colors.TRANSPARENT,
                )
            ),
            data=data if data is not None else idx,
            on_click=on_click,
        )

    def _on_file_master_click(self, e: ft.ControlEvent) -> None:
        label = getattr(e.control, "data", None)
        if (
            isinstance(label, str)
            and label != self._current_label
            and self.on_file_select
        ):
            self.on_file_select(label)

    def _on_item_master_click(self, e: ft.ControlEvent) -> None:
        idx = getattr(e.control, "data", 0)
        if isinstance(idx, int) and idx != self._selected_item:
            self._selected_item = idx
            self._rebuild_master()
            self._render_detail()
            try:
                self._detail.update()
            except RuntimeError:
                pass

    # -------------------------------------------------------------- category

    def _category_dir(self, category: tuple[str, ...]) -> str | None:
        prefix = "/".join(category) + "/"
        for label, path in self._files.items():
            if label.startswith(prefix):
                rest = len(label.split("/")) - len(category) - 1
                directory = os.path.dirname(path)
                for _ in range(rest):
                    directory = os.path.dirname(directory)
                return directory
        return None

    def _can_create_in(self, category: tuple[str, ...]) -> bool:
        return "/".join(category) in CREATE_CATEGORIES

    def _create_category_row(self, category: tuple[str, ...]) -> ft.Control:
        return ft.TextButton(
            content=ft.Row(
                [
                    ft.Icon(ft.Icons.ADD, size=16, color=ft.Colors.PRIMARY),
                    ft.Text(
                        "New entry",
                        size=12,
                        color=ft.Colors.PRIMARY,
                    ),
                ],
                spacing=6,
            ),
            style=ft.ButtonStyle(
                padding=ft.Padding(left=28, right=12, top=4, bottom=4),
                shape=ft.RoundedRectangleBorder(radius=0),
                side=None,
            ),
            on_click=lambda e, cp=category: self._on_category_add(cp),
        )

    def _on_category_add(self, category: tuple[str, ...]) -> None:
        name_field = ft.TextField(
            label="File name",
            hint_text="MyEntity.json",
            autofocus=True,
        )

        def confirm(ev: object) -> None:
            filename = name_field.value
            if not filename:
                return
            self._page.pop_dialog()
            self._page.update()
            self._create_category_file(category, filename)

        def cancel(ev: object) -> None:
            self._page.pop_dialog()

        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("New Config Entry"),
            content=ft.Column(
                [
                    ft.Text(f"Enter a name for the new file in {'/'.join(category)}:"),
                    name_field,
                ],
                tight=True,
                width=400,
            ),
            actions=[
                ft.TextButton("Cancel", on_click=cancel),
                ft.TextButton("Create", on_click=confirm),
            ],
        )
        self._page.show_dialog(dialog)
        self._page.update()

    def _create_category_file(self, category: tuple[str, ...], filename: str) -> None:
        filename = filename.strip()
        if not filename:
            return
        if not filename.lower().endswith(".json"):
            filename += ".json"
        directory = self._category_dir(category)
        if directory is None:
            logger.warning("No directory for category %s", "/".join(category))
            self._set_status("Cannot create: category directory not found")
            return
        path = os.path.join(directory, filename)
        if os.path.exists(path):
            self._set_status(f"Already exists: {filename}")
            return
        label = f"{'/'.join(category)}/{filename}"
        try:
            self._json_repo.save_doc(path, self._blank_template_for(category, path))
        except AccessError as ex:
            self._set_status(str(ex))
            return
        self._files[label] = path
        self._master_seed = None
        self._current_label = label
        if self.on_file_create:
            self.on_file_create(label, path)
        self._load_file_impl(path)

    def _blank_template_for(self, category: tuple[str, ...], path: str) -> object:
        sibling = self._first_sibling_path(category, path)
        if sibling is None:
            return {}
        try:
            doc = self._json_repo.load_doc(sibling)
        except (AccessError, ParseError):
            return {}
        return self._blank_doc(doc)

    def _first_sibling_path(self, category: tuple[str, ...], path: str) -> str | None:
        prefix = "/".join(category) + "/"
        directory = os.path.dirname(path)
        for sibling in self._files.values():
            if sibling != path and os.path.dirname(sibling) == directory:
                return sibling
        for label, sibling in self._files.items():
            if sibling != path and label.startswith(prefix):
                return sibling
        return None

    def _blank_doc(self, doc: object) -> object:
        if isinstance(doc, list):
            items = [o for o in doc if isinstance(o, dict)]
            return [self._blank_object(items[0])] if items else []
        if isinstance(doc, dict):
            return self._blank_object(doc)
        return {}

    def _blank_object(self, obj: dict[str, object]) -> dict[str, object]:
        out: dict[str, object] = {}
        for key, value in obj.items():
            if isinstance(value, dict):
                out[key] = self._blank_object(value) if value else {}
            elif isinstance(value, list):
                out[key] = self._blank_doc(value)
            elif isinstance(value, bool):
                out[key] = False
            elif isinstance(value, (int, float)):
                out[key] = 0
            else:
                out[key] = ""
        return out

    # ---------------------------------------------------------------- detail

    def _render_detail(self) -> None:
        node = self._doc_for_detail()
        if isinstance(node, dict):
            controls = self._render_object(node, self._schema, "detail")
        elif isinstance(node, list):
            if node and all(isinstance(o, dict) for o in node):
                controls = self._render_items_root(node)
            else:
                controls = self._render_list_root(node)
        else:
            controls = [ft.Text("Nothing to edit", italic=True)]
        self._detail.controls = controls

    def _render_object(
        self, node: dict[str, object], schema: FormSchema, _prefix: str
    ) -> list[ft.Control]:
        controls: list[ft.Control] = []
        for field in schema.fields:
            controls.append(self._render_field(node, field))
        for grid in schema.grids:
            controls.append(self._render_grid(node, grid))
        for lst in schema.lists:
            controls.append(self._render_list(node, lst))
        for dct in schema.dicts:
            controls.append(self._render_dict(node, dct))
        for group in schema.groups:
            controls.append(self._render_group(node, group))
        if (
            not schema.fields
            and not schema.grids
            and not schema.lists
            and not schema.dicts
            and not schema.groups
        ):
            controls.append(ft.Text("No editable fields", italic=True))
        return controls

    # -------------------------------------------------------------- controls

    def _mark_dirty(self) -> None:
        if not self._dirty:
            self._dirty = True

    def _field_widget(self, field: FormField, node: dict[str, object]) -> ft.Control:
        value = node.get(field.key)
        if field.type == FieldType.TOGGLE:
            cb = ft.Checkbox(
                value=value in (1, "1", True, "true", "yes", "on"),
                on_change=lambda e, n=node, k=field.key: self._on_toggle(
                    n, k, e.control.value
                ),
            )
            return ft.Container(
                content=cb,
                expand=True,
                alignment=ft.Alignment.CENTER_RIGHT,
            )
        if field.type == FieldType.BOOL:
            cb = ft.Checkbox(
                value=value in (True, 1, "1", "true", "yes", "on"),
                on_change=lambda e, n=node, k=field.key: self._on_bool(
                    n, k, e.control.value
                ),
            )
            return ft.Container(
                content=cb,
                expand=True,
                alignment=ft.Alignment.CENTER_RIGHT,
            )
        if field.type in (FieldType.INT, FieldType.FLOAT):
            tf = ft.TextField(
                value=_scalar_widget_value(field.type, value),
                dense=True,
                text_size=12,
                text_align=ft.TextAlign.RIGHT,
                keyboard_type=ft.KeyboardType.NUMBER,
                min_lines=1,
                max_lines=1,
                on_change=lambda e, n=node, k=field.key: self._on_text(
                    n, k, e.control.value
                ),
                expand=True,
            )
            return tf
        if field.type == FieldType.SINGLE_NAMED:
            dd = ft.Dropdown(
                value="" if value is None else str(value),
                dense=True,
                text_size=12,
                options=[ft.DropdownOption(key="", text="")]
                + [ft.DropdownOption(key=c) for c in field.options],
                on_select=lambda e, n=node, k=field.key: self._on_select(
                    n, k, e.control.value
                ),
                expand=True,
            )
            return dd
        tf = ft.TextField(
            value=_scalar_widget_value(FieldType.TEXT, value),
            dense=True,
            text_size=12,
            min_lines=1,
            max_lines=1,
            on_change=lambda e, n=node, k=field.key: self._on_text(
                n, k, e.control.value
            ),
            expand=True,
        )
        return tf

    def _form_row(self, label: str, widget: ft.Control) -> ft.Row:
        return ft.Row(
            [
                ft.Container(
                    content=ft.Text(label, size=12, weight=ft.FontWeight.W_500),
                    width=220,
                ),
                ft.Container(content=widget, expand=True),
            ],
            spacing=8,
        )

    def _render_field(self, node: dict[str, object], field: FormField) -> ft.Control:
        return self._form_row(field.label, self._field_widget(field, node))

    def _render_group(self, node: dict[str, object], group: FormGroup) -> ft.Control:
        child = node.get(group.key)
        if not isinstance(child, dict):
            child = {}
            node[group.key] = child
        children = self._render_object(child, group.schema, f"{group.key}.")
        return ft.ExpansionTile(
            title=ft.Text(group.label, size=13, weight=ft.FontWeight.BOLD),
            controls=[ft.Column(children, spacing=4)],
        )

    def _render_list(self, node: dict[str, object], lst: FormList) -> ft.Control:
        items = node.get(lst.key)
        if not isinstance(items, list):
            items = []
            node[lst.key] = items
        rows: list[ft.Control] = []
        for idx in range(len(items)):
            idx_fixed = idx
            widget = self._list_item_widget(lst, items, idx_fixed)
            delete = ft.IconButton(
                icon=ft.Icons.DELETE_OUTLINE,
                icon_size=18,
                tooltip="Remove",
                on_click=lambda e, i=idx_fixed, n=items: self._on_list_delete(n, i),
            )
            rows.append(ft.Row([widget, delete], spacing=4))
        add = ft.TextButton(
            "Add item",
            icon=ft.Icons.ADD,
            on_click=lambda e, n=items: self._on_list_add(n, lst),
        )
        return ft.ExpansionTile(
            title=ft.Text(lst.label, size=13, weight=ft.FontWeight.BOLD),
            controls=[ft.Column(rows, spacing=2), add],
        )

    def _list_item_widget(
        self, lst: FormList, items: list[object], idx: int
    ) -> ft.Control:
        value = items[idx] if idx < len(items) else None
        if lst.item_type in (FieldType.INT, FieldType.FLOAT):
            return ft.TextField(
                value=_scalar_widget_value(lst.item_type, value),
                dense=True,
                text_size=12,
                text_align=ft.TextAlign.RIGHT,
                keyboard_type=ft.KeyboardType.NUMBER,
                on_change=lambda e, i=idx, n=items, t=lst.item_type: self._on_list_text(
                    n, i, t, e.control.value
                ),
                expand=True,
            )
        tf = ft.TextField(
            value=_scalar_widget_value(FieldType.TEXT, value),
            dense=True,
            text_size=12,
            on_change=lambda e, i=idx, n=items, t=lst.item_type: self._on_list_text(
                n, i, t, e.control.value
            ),
            expand=True,
        )
        return tf

    def _render_grid(self, node: dict[str, object], grid: FormGrid) -> ft.Control:
        items = node.get(grid.key)
        if not isinstance(items, list):
            items = []
            node[grid.key] = items
        if grid.item_schema is not None:
            return self._render_grid_nested(items, grid)
        rows: list[ft.Control] = []
        for idx in range(len(items)):
            idx_fixed = idx
            row = self._render_grid_row(grid, items, idx_fixed)
            delete = ft.IconButton(
                icon=ft.Icons.DELETE_OUTLINE,
                icon_size=18,
                tooltip="Remove",
                on_click=lambda e, i=idx_fixed, n=items: self._on_grid_delete(n, i),
            )
            rows.append(ft.Row([row, delete], spacing=4))
        add = ft.TextButton(
            "Add item",
            icon=ft.Icons.ADD,
            on_click=lambda e, n=items, g=grid: self._on_grid_add(n, g),
        )
        header = ft.Row(
            [
                ft.Container(
                    content=ft.Text(col.label, size=11, weight=ft.FontWeight.BOLD),
                    width=180,
                )
                for col in grid.columns
            ],
            spacing=4,
        )
        return ft.ExpansionTile(
            title=ft.Text(grid.label, size=13, weight=ft.FontWeight.BOLD),
            controls=[
                ft.Column(
                    [
                        header,
                        ft.Column(rows, spacing=2),
                        add,
                    ],
                    spacing=2,
                )
            ],
        )

    def _render_grid_nested(self, items: list[object], grid: FormGrid) -> ft.Control:
        schema = grid.item_schema
        assert schema is not None
        rows: list[ft.Control] = []
        for idx in range(len(items)):
            idx_fixed = idx
            obj = items[idx] if idx < len(items) else {}
            if not isinstance(obj, dict):
                obj = {}
                items[idx] = obj
            label = self._grid_item_label(grid, obj, idx_fixed)
            children = self._render_object(obj, schema, f"{grid.key}.")
            header = ft.Row(
                [
                    ft.Container(
                        content=ft.Text(
                            label,
                            size=12,
                            weight=ft.FontWeight.W_600,
                            no_wrap=True,
                            overflow=ft.TextOverflow.ELLIPSIS,
                        ),
                        width=180,
                    ),
                    ft.IconButton(
                        icon=ft.Icons.DELETE_OUTLINE,
                        icon_size=18,
                        tooltip="Remove",
                        on_click=lambda e, i=idx_fixed, n=items: self._on_grid_delete(
                            n, i
                        ),
                    ),
                ],
                spacing=4,
            )
            rows.append(
                ft.ExpansionTile(
                    title=header,
                    controls=[
                        ft.Column(
                            [*children, ft.Row([])],
                            spacing=4,
                        )
                    ],
                )
            )
        add = ft.TextButton(
            "Add item",
            icon=ft.Icons.ADD,
            on_click=lambda e, n=items, g=grid: self._on_grid_add(n, g),
        )
        return ft.ExpansionTile(
            title=ft.Text(grid.label, size=13, weight=ft.FontWeight.BOLD),
            controls=[
                ft.Column(
                    [
                        ft.Column(rows, spacing=2),
                        add,
                    ],
                    spacing=2,
                )
            ],
        )

    def _grid_item_label(
        self, grid: FormGrid, item: dict[str, object], idx: int
    ) -> str:
        schema = grid.item_schema
        if schema is not None and schema.name_key:
            value = item.get(schema.name_key)
            if value is not None:
                return str(value)
        for candidate in ("DisplayName", "ClassName", "Name", "Title"):
            value = item.get(candidate)
            if value is not None:
                return str(value)
        if item:
            first_key = next(iter(item))
            return f"{first_key}: {item[first_key]}"
        return f"Item {idx + 1}"

    def _render_grid_row(self, grid: FormGrid, items: list[object], idx: int) -> ft.Row:
        obj = items[idx] if idx < len(items) else {}
        if not isinstance(obj, dict):
            obj = {}
            items[idx] = obj
        cells: list[ft.Control] = []
        for col in grid.columns:
            field = FormField(
                key=col.key, label=col.label, type=col.type, options=col.options
            )
            widget = self._field_widget(field, obj)
            cells.append(ft.Container(content=widget, width=180))
        return ft.Row(cells, spacing=4)

    def _render_dict(self, node: dict[str, object], dct: FormDict) -> ft.Control:
        mapping = node.get(dct.key)
        if not isinstance(mapping, dict):
            mapping = {}
            node[dct.key] = mapping
        rows: list[ft.Control] = []
        for idx, (key, _value) in enumerate(list(mapping.items())):
            idx_fixed = idx
            key_field = ft.TextField(
                value=str(key),
                dense=True,
                text_size=12,
                on_change=lambda e, i=idx_fixed, m=mapping, old=key: self._on_dict_key(
                    m, i, old, e.control.value
                ),
                expand=True,
            )
            value_widget = self._dict_value_widget(dct, mapping, key)
            delete = ft.IconButton(
                icon=ft.Icons.DELETE_OUTLINE,
                icon_size=18,
                tooltip="Remove",
                on_click=lambda e, k=key, m=mapping: self._on_dict_delete(m, k),
            )
            rows.append(ft.Row([key_field, value_widget, delete], spacing=4))
        add = ft.TextButton(
            "Add item",
            icon=ft.Icons.ADD,
            on_click=lambda e, m=mapping, d=dct: self._on_dict_add(m, d),
        )
        return ft.ExpansionTile(
            title=ft.Text(dct.label, size=13, weight=ft.FontWeight.BOLD),
            controls=[ft.Column(rows, spacing=2), add],
        )

    def _dict_value_widget(
        self, dct: FormDict, mapping: dict[str, object], key: str
    ) -> ft.Control:
        value = mapping.get(key)
        if dct.value_type in (FieldType.INT, FieldType.FLOAT):
            return ft.TextField(
                value=_scalar_widget_value(dct.value_type, value),
                dense=True,
                text_size=12,
                text_align=ft.TextAlign.RIGHT,
                keyboard_type=ft.KeyboardType.NUMBER,
                on_change=lambda e, k=key, m=mapping, t=dct.value_type: (
                    self._on_dict_value(m, k, t, e.control.value)
                ),
                width=140,
            )
        tf = ft.TextField(
            value=_scalar_widget_value(FieldType.TEXT, value),
            dense=True,
            text_size=12,
            on_change=lambda e, k=key, m=mapping, t=dct.value_type: self._on_dict_value(
                m, k, t, e.control.value
            ),
            width=140,
        )
        return tf

    def _render_list_root(self, node: list[object]) -> list[ft.Control]:
        rows: list[ft.Control] = []
        for idx, item in enumerate(node):
            rows.append(ft.Text(str(item), size=12))
        if not rows:
            rows.append(ft.Text("Empty list", italic=True))
        return rows

    def _render_items_root(self, items: list[object]) -> list[ft.Control]:
        schema = self._schema
        rows: list[ft.Control] = []
        for idx in range(len(items)):
            idx_fixed = idx
            obj = items[idx] if idx < len(items) else {}
            if not isinstance(obj, dict):
                obj = {}
                items[idx] = obj
            label = self._root_item_label(obj, idx_fixed)
            children = self._render_object(obj, schema, "item")
            header = ft.Row(
                [
                    ft.Container(
                        content=ft.Text(
                            label,
                            size=12,
                            weight=ft.FontWeight.W_600,
                            no_wrap=True,
                            overflow=ft.TextOverflow.ELLIPSIS,
                        ),
                        width=180,
                    ),
                    ft.IconButton(
                        icon=ft.Icons.DELETE_OUTLINE,
                        icon_size=18,
                        tooltip="Remove",
                        on_click=lambda e, i=idx_fixed: self._on_root_delete(i),
                    ),
                ],
                spacing=4,
            )
            rows.append(
                ft.ExpansionTile(
                    title=header,
                    controls=[
                        ft.Column(
                            [*children, ft.Row([])],
                            spacing=4,
                        )
                    ],
                )
            )
        add = ft.TextButton(
            "Add item",
            icon=ft.Icons.ADD,
            on_click=lambda e: self._on_root_add(),
        )
        return [*rows, add]

    def _root_item_label(self, item: dict[str, object], idx: int) -> str:
        schema = self._schema
        if schema.name_key:
            value = item.get(schema.name_key)
            if value is not None:
                return str(value)
        for candidate in ("DisplayName", "ClassName", "Name", "Title"):
            value = item.get(candidate)
            if value is not None:
                return str(value)
        return f"Item {idx + 1}"

    def _on_root_add(self) -> None:
        if isinstance(self._doc, list):
            self._doc.append({})
            self._mark_dirty()
            self._render_detail()
            try:
                self._detail.update()
            except RuntimeError:
                pass

    def _on_root_delete(self, idx: int) -> None:
        if isinstance(self._doc, list) and 0 <= idx < len(self._doc):
            self._doc.pop(idx)
            self._mark_dirty()
            self._render_detail()
            try:
                self._detail.update()
            except RuntimeError:
                pass

    # ------------------------------------------------------------ mutations

    def _on_text(self, node: dict[str, object], key: str, text: str) -> None:
        node[key] = text
        self._mark_dirty()

    def _on_select(self, node: dict[str, object], key: str, text: str) -> None:
        node[key] = text
        self._mark_dirty()

    def _on_toggle(self, node: dict[str, object], key: str, checked: bool) -> None:
        node[key] = 1 if checked else 0
        self._mark_dirty()

    def _on_bool(self, node: dict[str, object], key: str, checked: bool) -> None:
        node[key] = bool(checked)
        self._mark_dirty()

    def _on_list_text(
        self, items: list[object], idx: int, ftype: FieldType, text: str
    ) -> None:
        if idx < len(items):
            items[idx] = text
        self._mark_dirty()

    def _on_list_add(self, items: list[object], lst: FormList) -> None:
        default: object = (
            "" if lst.item_type not in (FieldType.INT, FieldType.FLOAT) else 0
        )
        items.append(default)
        self._mark_dirty()
        self._render_detail()
        try:
            self._detail.update()
        except RuntimeError:
            pass

    def _on_list_delete(self, items: list[object], idx: int) -> None:
        if 0 <= idx < len(items):
            items.pop(idx)
            self._mark_dirty()
            self._render_detail()
            try:
                self._detail.update()
            except RuntimeError:
                pass

    def _on_grid_add(self, items: list[object], grid: FormGrid) -> None:
        items.append({})
        self._mark_dirty()
        self._render_detail()
        try:
            self._detail.update()
        except RuntimeError:
            pass

    def _on_grid_delete(self, items: list[object], idx: int) -> None:
        if 0 <= idx < len(items):
            items.pop(idx)
            self._mark_dirty()
            self._render_detail()
            try:
                self._detail.update()
            except RuntimeError:
                pass

    def _on_dict_key(
        self, mapping: dict[str, object], idx: int, old_key: str, new_key: str
    ) -> None:
        if not new_key or new_key == old_key:
            return
        if old_key in mapping and new_key not in mapping:
            mapping[new_key] = mapping.pop(old_key)
        self._mark_dirty()
        self._render_detail()
        try:
            self._detail.update()
        except RuntimeError:
            pass

    def _on_dict_value(
        self,
        mapping: dict[str, object],
        key: str,
        ftype: FieldType,
        text: str,
    ) -> None:
        mapping[key] = text
        self._mark_dirty()

    def _on_dict_add(self, mapping: dict[str, object], dct: FormDict) -> None:
        default: object = (
            "" if dct.value_type not in (FieldType.INT, FieldType.FLOAT) else 0
        )
        suffix = 1
        key = "newKey"
        while key in mapping:
            suffix += 1
            key = f"newKey{suffix}"
        mapping[key] = default
        self._mark_dirty()
        self._render_detail()
        try:
            self._detail.update()
        except RuntimeError:
            pass

    def _on_dict_delete(self, mapping: dict[str, object], key: str) -> None:
        mapping.pop(key, None)
        self._mark_dirty()
        self._render_detail()
        try:
            self._detail.update()
        except RuntimeError:
            pass

    # ----------------------------------------------------------------- save

    def _save_current_file(self) -> None:
        target = self._path
        if target is None:
            return
        try:
            doc = self._coerce_doc()
            self._json_repo.save_doc(target, doc)
            self._doc = doc
            self._dirty = False
            self._set_status("Saved")
            if self.on_saved:
                self.on_saved()
        except Exception as exc:
            logger.error("Form save failed for %s: %s", target, exc)
            self._set_status(f"Error saving: {exc}")

    def _coerce_doc(self) -> object:
        if self._master_mode == "items" and isinstance(self._doc, list):
            items = self._doc
            return [
                self._coerce_object(item, self._schema)
                for item in items
                if isinstance(item, dict)
            ]
        if isinstance(self._doc, list) and all(isinstance(o, dict) for o in self._doc):
            return [
                self._coerce_object(item, self._schema)
                for item in self._doc
                if isinstance(item, dict)
            ]
        if isinstance(self._doc, dict):
            return self._coerce_object(self._doc, self._schema)
        return self._doc

    def _coerce_object(
        self, node: dict[str, object], schema: FormSchema
    ) -> dict[str, object]:
        out: dict[str, object] = {}
        for field in schema.fields:
            if field.key in node:
                out[field.key] = _human_coerce(field.type, node[field.key])
        for grid in schema.grids:
            value = node.get(grid.key)
            if isinstance(value, list):
                out[grid.key] = [
                    self._coerce_object(item, self._schema_for_item(grid))
                    for item in value
                    if isinstance(item, dict)
                ]
            elif value is not None:
                out[grid.key] = value
        for lst in schema.lists:
            value = node.get(lst.key)
            if isinstance(value, list):
                out[lst.key] = [_human_coerce(lst.item_type, v) for v in value]
            elif value is not None:
                out[lst.key] = value
        for dct in schema.dicts:
            value = node.get(dct.key)
            if isinstance(value, dict):
                out[dct.key] = {
                    str(k): _human_coerce(dct.value_type, v) for k, v in value.items()
                }
            elif value is not None:
                out[dct.key] = value
        for group in schema.groups:
            value = node.get(group.key)
            if isinstance(value, dict):
                out[group.key] = self._coerce_object(value, group.schema)
            elif value is not None:
                out[group.key] = value
        for key, value in node.items():
            if key not in out:
                out[key] = value
        return out

    @staticmethod
    def _schema_for_item(grid: FormGrid) -> FormSchema:
        if grid.item_schema is not None:
            return grid.item_schema
        return FormSchema(
            fields=grid.columns,
        )
