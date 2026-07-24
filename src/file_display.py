from lxml import etree as ET
from dataclasses import dataclass

import flet as ft

PAGE_SIZE = 100

_cache: dict[str, list[RowData]] = {}
_cache_trees: dict[str, ET.ElementTree] = {}


def _elem_text(parent: ET.Element, tag: str, default: str = "") -> str:
    elem = parent.find(tag)
    if elem is not None and elem.text:
        return elem.text.strip()
    return default


def _set_elem_text(parent: ET.Element, tag: str, value: str) -> None:
    elem = parent.find(tag)
    if elem is not None:
        if value:
            elem.text = value
        else:
            parent.remove(elem)
    elif value:
        ET.SubElement(parent, tag).text = value


def _flags_to_str(flags_elem: ET.Element | None) -> str:
    if flags_elem is None:
        return ""
    return ", ".join(f"{k}={v}" for k, v in flags_elem.attrib.items())


def _str_to_flags(s: str) -> dict[str, str]:
    result = {}
    for part in s.split(","):
        part = part.strip()
        if "=" in part:
            k, v = part.split("=", 1)
            result[k.strip()] = v.strip()
    return result


def _names_to_str(elems: list[ET.Element]) -> str:
    names = [e.get("name", "") for e in elems if e.get("name")]
    return ", ".join(names)


def _build_row(type_elem: ET.Element) -> RowData:
    cat_elem = type_elem.find("category")
    return RowData(
            fields=[
            type_elem.get("name", ""),
            _elem_text(type_elem, "nominal"),
            _elem_text(type_elem, "lifetime"),
            _elem_text(type_elem, "restock"),
            _elem_text(type_elem, "min"),
            _elem_text(type_elem, "quantmin"),
            _elem_text(type_elem, "quantmax"),
            _elem_text(type_elem, "cost"),
            _flags_to_str(type_elem.find("flags")),
            cat_elem.get("name", "") if cat_elem is not None else "",
            _names_to_str(type_elem.findall("usage")),
            _names_to_str(type_elem.findall("value")),
        ],
        elem=type_elem)


_COL_FLEX = [3, 1, 1, 1, 1, 1, 1, 1, 4, 2, 1, 3]
_ALIGN = [
    ft.TextAlign.LEFT, ft.TextAlign.RIGHT, ft.TextAlign.RIGHT, ft.TextAlign.RIGHT,
    ft.TextAlign.RIGHT, ft.TextAlign.RIGHT, ft.TextAlign.RIGHT, ft.TextAlign.RIGHT,
    ft.TextAlign.LEFT, ft.TextAlign.LEFT, ft.TextAlign.LEFT, ft.TextAlign.LEFT,
]

COLUMNS = [
    ft.DataColumn(label=ft.Text("Name")),
    ft.DataColumn(label=ft.Text("Nominal")),
    ft.DataColumn(label=ft.Text("Lifetime")),
    ft.DataColumn(label=ft.Text("Restock")),
    ft.DataColumn(label=ft.Text("Min")),
    ft.DataColumn(label=ft.Text("QuantMin")),
    ft.DataColumn(label=ft.Text("QuantMax")),
    ft.DataColumn(label=ft.Text("Cost")),
    ft.DataColumn(label=ft.Text("Flags")),
    ft.DataColumn(label=ft.Text("Category")),
    ft.DataColumn(label=ft.Text("Usage"), tooltip="Comma separated"),
    ft.DataColumn(label=ft.Text("Value")),
]


@dataclass
class RowData:
    fields: list[str]
    elem: ET.Element


class FileDisplay:
    def __init__(self):
        self._path: str | None = None
        self._rows: list[RowData] = []
        self._filtered: list[int] = []
        self._page: int = 0
        self._dirty: bool = False
        self._syncing: bool = False
        self._prev_count: int = 0

        self._save_status = ft.Text("", size=12)
        self._page_info = ft.Text("", size=12)
        self._prev_btn = ft.Button("Prev", on_click=self._prev_page)
        self._next_btn = ft.Button("Next", on_click=self._next_page)
        self._search_field = ft.TextField(
            label="Search",
            dense=True,
            text_size=12,
            width=250,
            on_submit=self._on_search,
            on_change=self._on_search,
        )

        self._pool_fields: list[list[ft.TextField]] = []
        self._pool_rows: list[ft.DataRow] = []
        for _ in range(PAGE_SIZE):
            fields = []
            for i in range(12):
                kw = dict(
                    value="", dense=True, text_size=12, text_align=_ALIGN[i],
                    min_lines=1, max_lines=1,
                    on_change=self._on_field_change,
                )
                if i == 10:
                    kw["width"] = 200
                else:
                    kw["expand"] = True
                fields.append(ft.TextField(**kw))
            self._pool_fields.append(fields)
            self._pool_rows.append(ft.DataRow(cells=[ft.DataCell(f) for f in fields]))

        self._data_table = ft.DataTable(
            columns=COLUMNS,
            rows=[],
            expand=True,
            column_spacing=6,
            data_row_min_height=34,
            heading_row_height=36,
            horizontal_lines=ft.border.BorderSide(1, ft.Colors.OUTLINE_VARIANT),
        )

        self.control = ft.Container(
            visible=False,
            expand=True,
            content=ft.Column(
                [
                    ft.Row(
                        [ft.Button("Save", icon=ft.Icons.SAVE, on_click=self._save), self._save_status],
                        alignment=ft.MainAxisAlignment.START,
                    ),
                    ft.Container(
                        content=ft.Column(
                            [ft.Row([self._data_table], scroll=ft.ScrollMode.ALWAYS)],
                            scroll=ft.ScrollMode.AUTO,
                            expand=True,
                        ),
                        border=ft.border.Border(
                            ft.border.BorderSide(1, ft.Colors.OUTLINE_VARIANT),
                            ft.border.BorderSide(1, ft.Colors.OUTLINE_VARIANT),
                            ft.border.BorderSide(1, ft.Colors.OUTLINE_VARIANT),
                            ft.border.BorderSide(1, ft.Colors.OUTLINE_VARIANT),
                        ),
                        border_radius=8,
                        expand=True,
                    ),
                    ft.Row(
                        [
                            self._prev_btn,
                            self._page_info,
                            self._next_btn,
                            self._search_field,
                        ],
                        alignment=ft.MainAxisAlignment.CENTER,
                    ),
                ],
                expand=True,
            ),
        )

    def load_file(self, path: str) -> None:
        self._path = path
        self._save_status.value = ""
        self._page = 0
        self._search_field.value = ""
        self._dirty = False
        self._prev_count = 0

        if path in _cache:
            self._rows = _cache[path]
        else:
            try:
                tree = ET.parse(path)
                _cache_trees[path] = tree
                root = tree.getroot()
                self._rows = [_build_row(t) for t in root.findall("type")]
                _cache[path] = self._rows
            except Exception as ex:
                self.control.content = ft.Container(
                    content=ft.Text(f"Error parsing file: {ex}", selectable=True),
                    padding=10,
                )
                self.control.visible = True
                return

        self._apply_filter("")
        self._render_page()
        self.control.visible = True

    def _on_field_change(self, e) -> None:
        if not self._syncing:
            self._dirty = True

    def _sync_page_back(self) -> None:
        if self._path is None or not self._dirty:
            return
        start = self._page * PAGE_SIZE
        for i in range(len(self._data_table.rows)):
            row_idx = self._filtered[start + i] if start + i < len(self._filtered) else -1
            if row_idx < 0:
                break
            for j in range(12):
                self._rows[row_idx].fields[j] = self._pool_fields[i][j].value
        self._dirty = False

    def _apply_filter(self, query: str) -> None:
        if not query:
            self._filtered = list(range(len(self._rows)))
        else:
            self._filtered = [
                i for i, row in enumerate(self._rows)
                if query in row.fields[0].lower()
            ]

    def _render_page(self) -> None:
        total = len(self._filtered)
        total_pages = max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE)
        self._page = max(0, min(self._page, total_pages - 1))

        start = self._page * PAGE_SIZE
        end = min(start + PAGE_SIZE, total)
        count = end - start

        self._syncing = True
        for i in range(count):
            row = self._rows[self._filtered[start + i]].fields
            for j in range(12):
                field = self._pool_fields[i][j]
                if field.value != row[j]:
                    field.value = row[j]
        self._syncing = False

        if self._prev_count != count:
            self._data_table.rows = self._pool_rows[:count]
            self._prev_count = count

        self._page_info.value = f"Page {self._page + 1}/{total_pages}  ({total} rows)"
        self._prev_btn.disabled = self._page <= 0
        self._next_btn.disabled = self._page >= total_pages - 1

    def _prev_page(self, e) -> None:
        self._sync_page_back()
        self._page -= 1
        self._render_page()
        self._data_table.update()

    def _next_page(self, e) -> None:
        self._sync_page_back()
        self._page += 1
        self._render_page()
        self._data_table.update()

    def _on_search(self, e) -> None:
        self._sync_page_back()
        query = (self._search_field.value or "").strip().lower()
        self._apply_filter(query)
        self._page = 0
        self._render_page()
        self.control.update()

    def _save(self, e) -> None:
        self._sync_page_back()
        if self._path is None:
            return
        tree = _cache_trees.get(self._path)
        if tree is None:
            return
        try:
            root = tree.getroot()
            for row_data in self._rows:
                row = row_data.fields
                elem = row_data.elem
                elem.set("name", row[0])
                _set_elem_text(elem, "nominal", row[1])
                _set_elem_text(elem, "lifetime", row[2])
                _set_elem_text(elem, "restock", row[3])
                _set_elem_text(elem, "min", row[4])
                _set_elem_text(elem, "quantmin", row[5])
                _set_elem_text(elem, "quantmax", row[6])
                _set_elem_text(elem, "cost", row[7])
                self._update_flags(elem, row[8])
                self._update_single_named(elem, "category", row[9])
                self._update_multi_named(elem, "usage", row[10])
                self._update_multi_named(elem, "value", row[11])
            ET.indent(tree, space="\t")
            tree.write(self._path, encoding="UTF-8", xml_declaration=True)
            self._save_status.value = "Saved"
            self._save_status.color = ft.Colors.GREEN
        except Exception as ex:
            self._save_status.value = f"Save error: {ex}"
            self._save_status.color = ft.Colors.RED

    def _update_flags(self, parent: ET.Element, flags_str: str) -> None:
        f = parent.find("flags")
        if not flags_str.strip():
            if f is not None:
                parent.remove(f)
            return
        if f is None:
            f = ET.SubElement(parent, "flags")
        f.attrib.clear()
        f.attrib.update(_str_to_flags(flags_str))

    def _update_single_named(self, parent: ET.Element, tag: str, name: str) -> None:
        elems = parent.findall(tag)
        existing = elems[0] if elems else None
        if name.strip():
            if existing is not None:
                existing.set("name", name.strip())
            else:
                ET.SubElement(parent, tag).set("name", name.strip())
        else:
            if existing is not None:
                parent.remove(existing)

    def _update_multi_named(self, parent: ET.Element, tag: str, s: str) -> None:
        for elem in parent.findall(tag):
            parent.remove(elem)
        for part in s.split(","):
            part = part.strip()
            if part:
                ET.SubElement(parent, tag).set("name", part)

    def clear(self) -> None:
        self._path = None
        self._rows = []
        self._filtered = []
        self._data_table.rows = []
        self._save_status.value = ""
        self.control.visible = False
        self._dirty = False
        self._prev_count = 0
