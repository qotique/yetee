from __future__ import annotations

import logging

import flet as ft

from event_display import EventDisplay
from file_display import FileDisplay
from models.project import Project
from services.config_service import ConfigService
from services.economy_service import EconomyService
from services.entertainment_service import EntertainmentService
from repository.event_repository import EventRepository
from repository.file_cache import FileCache
from repository.xml_repository import XmlRepository

logger = logging.getLogger(__name__)

ENTITY_LABELS: dict[str, str] = {
    "types.xml": "Types",
    "events.xml": "Events",
    "globals.xml": "Globals",
    "cfgspawnabletypes.xml": "Spawnable Types",
    "cfgrandompresets.xml": "Random Presets",
}

TYPES_ENTITY = "Types"
SINGLE_FILE_ENTITIES: set[str] = {
    "Events",
    "Globals",
    "Spawnable Types",
    "Random Presets",
}
ADD_TAB_LABEL = "+"


def _get_entity(filename: str) -> str:
    return ENTITY_LABELS.get(filename, "Types")


class EconomyEditor:
    def __init__(
        self,
        page: ft.Page,
        config_service: ConfigService | None = None,
        entertainment_service: EntertainmentService | None = None,
        file_cache: FileCache | None = None,
    ):
        self._page = page
        self._config_service: ConfigService | None = config_service
        self._entertainment_service = entertainment_service
        self._cache: FileCache = file_cache or FileCache()
        self._xml_repo = XmlRepository(cache=self._cache)

        self._project: Project | None = None
        self._entities: dict[str, dict[str, str]] = {}
        self._current_entity: str | None = None
        self._current_file: str | None = None
        self._add_tab_index: int | None = None

        self._file_display = FileDisplay(
            page=self._page,
            xml_repo=self._xml_repo,
            cache=self._cache,
            entertainment_service=self._entertainment_service,
        )

        self._event_display = EventDisplay(
            page=self._page,
            event_repo=EventRepository(cache=self._cache),
            cache=self._cache,
        )

        self._content_slot = ft.Container(
            expand=True, content=self._file_display.control
        )

        self._using_event_display: bool = False

        self._load_seq: int = 0
        self._tabs: ft.Tabs | None = None
        self._events_file_path: str | None = None
        self._spawns_file_path: str | None = None

        self._empty_title = ft.Text(
            "Open a project to start editing", size=16, italic=True
        )
        self._empty_hint = ft.Text(
            "Use Project > New Project or select from the dropdown",
            size=13,
            color=ft.Colors.GREY_500,
        )
        self._empty_label = ft.Container(
            expand=True,
            content=ft.Column(
                [self._empty_title, self._empty_hint],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                alignment=ft.MainAxisAlignment.CENTER,
                expand=True,
            ),
        )

        self._editor_stack = ft.Column(
            [self._content_slot],
            expand=True,
            visible=False,
        )

        self.control = ft.Container(
            expand=True,
            content=ft.Stack(
                [self._empty_label, self._editor_stack],
                expand=True,
            ),
        )

    def load_project(self, project: Project) -> None:
        self._project = project
        svc = EconomyService()
        economy_dir = project.economy_dir

        type_files = svc.get_type_files(economy_dir)
        types_dir = svc.get_types_dir(economy_dir)
        known_files = svc.get_known_files(types_dir) if types_dir else {}
        economy_dir_files = svc.get_economy_dir_files(economy_dir)

        self._entities = {}
        self._current_entity = None
        self._current_file = None

        type_file_map: dict[str, str] = {}
        for fname, fpath in type_files.items():
            type_file_map[_get_label(fname)] = fpath
        self._entities[TYPES_ENTITY] = type_file_map

        for fname, fpath in known_files.items():
            if fname not in type_files:
                entity = _get_entity(fname)
                label = _get_label(fname)
                self._entities[entity] = {label: fpath}

        self._events_file_path = known_files.get("events.xml")
        self._spawns_file_path = economy_dir_files.get("cfgeventspawns.xml")

        self._editor_stack.visible = True
        self._empty_label.visible = False
        try:
            self.control.update()
        except RuntimeError:
            pass
        first_entity = next(iter(self._entities))
        self.switch_entity(first_entity)
        try:
            self.control.update()
        except RuntimeError:
            pass

    def unload(self) -> None:
        self._load_seq += 1
        self._file_display.clear()
        self._event_display.clear()
        self._project = None
        self._entities = {}
        self._current_entity = None
        self._current_file = None
        self._events_file_path = None
        self._spawns_file_path = None
        self._clear_tabs()
        self._content_slot.content = self._file_display.control
        self._editor_stack.controls = [self._content_slot]
        self._editor_stack.visible = False
        self._empty_title.value = "Open a project to start editing"
        self._empty_hint.value = "Use Project > New Project or select from the dropdown"
        self._empty_label.visible = True
        try:
            self.control.update()
        except RuntimeError:
            pass

    def switch_entity(self, entity: str) -> None:
        if entity == self._current_entity or entity not in self._entities:
            return
        self._file_display.save_file()
        self._file_display.clear()
        self._event_display.clear()
        self._clear_tabs()
        files = self._entities[entity]
        file_labels = list(files.keys())
        self._current_entity = entity
        self._using_event_display = entity == "Events"

        if self._using_event_display:
            self._content_slot.content = self._event_display.control
            self._editor_stack.controls = [
                self._event_display._button_row,
                self._content_slot,
            ]
            self._current_file = None
            try:
                self.control.update()
            except RuntimeError:
                pass
            self._schedule_event_load()
        else:
            show_add = entity == TYPES_ENTITY
            self._build_tabs(file_labels, show_add)
            self._content_slot.content = self._file_display.control
            self._editor_stack.controls = [
                self._file_display._button_row,
                self._tabs,
                self._content_slot,
            ]
            if file_labels:
                self._current_file = file_labels[0]
            else:
                self._current_file = None
            try:
                self.control.update()
            except RuntimeError:
                pass
            self._schedule_load()

    def switch_file(self, label: str) -> None:
        if self._current_entity is None or self._current_entity not in self._entities:
            return
        files = self._entities[self._current_entity]
        if label == self._current_file or label not in files:
            logger.info("SWITCH skip %s (current=%s)", label, self._current_file)
            return
        logger.info("SWITCH %s -> %s", self._current_file, label)
        self._file_display.save_file()
        self._file_display.clear()
        self._current_file = label
        try:
            self.control.update()
        except RuntimeError:
            pass
        self._schedule_load()

    def save_file(self) -> None:
        self._file_display.save_file()
        self._event_display.save_file()

    def save_current(self, e: object = None) -> None:
        if self._using_event_display:
            self._event_display._save(e)
        else:
            self._file_display._save(e)

    @property
    def project(self) -> Project | None:
        return self._project

    @property
    def file_display(self) -> FileDisplay:
        return self._file_display

    @property
    def available_entities(self) -> list[str]:
        return list(self._entities.keys())

    @property
    def current_entity(self) -> str | None:
        return self._current_entity

    @property
    def current_file(self) -> str | None:
        return self._current_file

    @property
    def entity_files(self) -> list[str]:
        if self._current_entity is None or self._current_entity not in self._entities:
            return []
        return list(self._entities[self._current_entity].keys())

    @property
    def is_types_entity(self) -> bool:
        return self._current_entity == TYPES_ENTITY

    @property
    def economy_dir(self) -> str | None:
        return self._project.economy_dir if self._project else None

    def get_file_path(self, label: str) -> str | None:
        for files in self._entities.values():
            if label in files:
                return files[label]
        return None

    def _schedule_load(self) -> None:
        self._load_seq += 1
        seq = self._load_seq
        logger.info("SCHEDULE seq=%d file=%s", seq, self._current_file)
        try:
            self._page.run_task(self._load_current_file_async, seq)
        except RuntimeError:
            pass

    def _schedule_event_load(self) -> None:
        self._load_seq += 1
        seq = self._load_seq
        logger.info("SCHEDULE_EVENT seq=%d", seq)
        try:
            self._page.run_task(self._load_events_async, seq)
        except RuntimeError:
            pass

    async def _load_events_async(self, seq: int) -> None:
        if seq != self._load_seq:
            logger.info("ABORT stale event seq=%d cur_seq=%d", seq, self._load_seq)
            return
        if self._events_file_path is None:
            logger.warning("No events file path")
            return
        logger.info("LOADING events seq=%d path=%s", seq, self._events_file_path)
        try:
            self._event_display.load_file(
                self._events_file_path, self._spawns_file_path
            )
        except RuntimeError:
            pass
        logger.info("DONE loading events seq=%d", seq)

    async def _load_current_file_async(self, seq: int) -> None:
        if seq != self._load_seq:
            logger.info("ABORT stale seq=%d cur_seq=%d", seq, self._load_seq)
            return
        if self._current_entity is None or self._current_file is None:
            return
        files = self._entities.get(self._current_entity)
        if files is None or self._current_file not in files:
            return
        path = files[self._current_file]
        logger.info("LOADING seq=%d file=%s path=%s", seq, self._current_file, path)
        try:
            await self._file_display.load_file_async(
                path, cancel_check=lambda: seq != self._load_seq
            )
        except RuntimeError:
            pass
        logger.info("DONE seq=%d file=%s", seq, self._current_file)

    def _build_tabs(self, file_labels: list[str], show_add: bool = False) -> None:
        labels = list(file_labels)
        if show_add:
            labels.append(ADD_TAB_LABEL)
            self._add_tab_index = len(labels) - 1
        else:
            self._add_tab_index = None
        tab_bar = ft.TabBar(
            tabs=[ft.Tab(label=lb) for lb in labels],
            on_click=self._on_tab_change,
        )
        self._tabs = ft.Tabs(
            content=tab_bar,
            length=len(labels),
            selected_index=0,
        )

    def _clear_tabs(self) -> None:
        self._tabs = None
        self._add_tab_index = None

    def _on_tab_change(self, e: object) -> None:
        if self._tabs is None:
            return
        try:
            idx = int(getattr(e, "data", -1))
        except (ValueError, TypeError):
            return
        if idx < 0:
            return
        if self._add_tab_index is not None and idx == self._add_tab_index:
            self._on_add_tab()
            return
        files = self.entity_files
        if idx >= len(files):
            return
        self.switch_file(files[idx])

    def _on_add_tab(self) -> None:
        name_field = ft.TextField(
            label="File name",
            hint_text="my_types.xml",
            autofocus=True,
        )

        def confirm(ev: object) -> None:
            filename = name_field.value
            if not filename:
                return
            self._page.pop_dialog()
            self._page.update()
            self._create_type_file(filename)

        def cancel(ev: object) -> None:
            self._page.pop_dialog()

        dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("New Type File"),
            content=ft.Column(
                [
                    ft.Text("Enter a name for the new type file:"),
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

    def _create_type_file(self, filename: str) -> None:
        if not filename.endswith(".xml"):
            filename += ".xml"
        if self._project is None:
            return
        economy_dir = self._project.economy_dir
        cs = self._config_service or ConfigService()
        config_path = EconomyService().find_config(economy_dir)
        if config_path is None:
            logger.error("cfgeconomycore.xml not found in %s", economy_dir)
            return
        file_path = cs.create_type_file(config_path, filename)
        if file_path is None:
            logger.error("Failed to create type file %s", filename)
            return
        svc = EconomyService()
        type_files = svc.get_type_files(economy_dir)
        type_file_map: dict[str, str] = {}
        for fname, fpath in type_files.items():
            type_file_map[_get_label(fname)] = fpath
        self._entities[TYPES_ENTITY] = type_file_map

        label = _get_label(filename)
        self._build_tabs(list(type_file_map.keys()), show_add=True)
        self._editor_stack.controls = [
            self._file_display._button_row,
            self._tabs,
            self._content_slot,
        ]
        self.control.update()
        if label in type_file_map:
            self.switch_file(label)


def _get_label(filename: str) -> str:
    return ENTITY_LABELS.get(
        filename, filename.replace(".xml", "").replace("_", " ").title()
    )
