from __future__ import annotations

from collections.abc import Callable
import logging
import os
from typing import TypeAlias

import flet as ft

from event_display import EventDisplay
from file_display import FileDisplay
from form_display import FormDisplay
from form_schema import entity_has_form_schemas
from models.project import Project
from mod_handlers import is_not_yet_available
from custom_entities import is_registered_entity
from settings_table_display import SettingsTableDisplay
from services.config_service import ConfigService
from services.economy_service import EconomyService
from protocols import IProfileService
from unavailable_display import UnavailableDisplay

logger = logging.getLogger(__name__)

ENTITY_LABELS: dict[str, str] = {
    "types.xml": "Types",
    "events.xml": "Events",
    "globals.xml": "Globals",
    "cfgspawnabletypes.xml": "Spawnable Types",
    "cfgrandompresets.xml": "Random Presets",
}

TYPES_ENTITY = "Types"
ADD_TAB_LABEL = "+"

DisplayWidget: TypeAlias = (
    FileDisplay | EventDisplay | SettingsTableDisplay | UnavailableDisplay | FormDisplay
)


class _EntityConfig:
    __slots__ = ("display", "show_tabs", "show_add_tab", "schedule_load")

    def __init__(
        self,
        display: DisplayWidget,
        show_tabs: bool = True,
        show_add_tab: bool = False,
        schedule_load: Callable[[], None] | None = None,
    ) -> None:
        self.display = display
        self.show_tabs = show_tabs
        self.show_add_tab = show_add_tab
        self.schedule_load = schedule_load


def _get_entity(filename: str) -> str:
    return ENTITY_LABELS.get(filename, "Types")


class EconomyEditor:
    def __init__(
        self,
        page: ft.Page,
        file_display: FileDisplay,
        event_display: EventDisplay,
        config_service: ConfigService | None = None,
        profile_service: IProfileService | None = None,
        settings_display: SettingsTableDisplay | None = None,
        form_display: FormDisplay | None = None,
        unavailable_display: UnavailableDisplay | None = None,
    ):
        self._page = page
        self._config_service: ConfigService | None = config_service
        self._profile_service: IProfileService | None = profile_service

        self._project: Project | None = None
        self._entities: dict[str, dict[str, str]] = {}
        self._current_entity: str | None = None
        self._current_file: str | None = None
        self._add_tab_index: int | None = None

        self._file_display = file_display
        self._event_display = event_display
        self._settings_display = settings_display
        self._form_display = form_display
        self._unavailable_display = unavailable_display

        self._content_slot = ft.Container(
            expand=True, content=self._file_display.control
        )

        self._entity_configs: dict[str, _EntityConfig] = {
            TYPES_ENTITY: _EntityConfig(
                display=self._file_display,
                show_tabs=True,
                show_add_tab=True,
                schedule_load=self._schedule_load,
            ),
            "Events": _EntityConfig(
                display=self._event_display,
                show_tabs=False,
                schedule_load=self._schedule_event_load,
            ),
            "Globals": _EntityConfig(
                display=self._file_display,
                show_tabs=False,
                schedule_load=self._schedule_load,
            ),
            "Spawnable Types": _EntityConfig(
                display=self._file_display,
                show_tabs=False,
                schedule_load=self._schedule_load,
            ),
            "Random Presets": _EntityConfig(
                display=self._file_display,
                show_tabs=False,
                schedule_load=self._schedule_load,
            ),
        }

        if self._settings_display is not None:
            self._settings_entity_config: _EntityConfig | None = _EntityConfig(
                display=self._settings_display,
                show_tabs=True,
                schedule_load=self._schedule_settings_load,
            )
        else:
            self._settings_entity_config = None

        if self._form_display is not None:
            self._form_entity_config: _EntityConfig | None = _EntityConfig(
                display=self._form_display,
                show_tabs=False,
                schedule_load=self._schedule_settings_load,
            )
        else:
            self._form_entity_config = None

        if self._unavailable_display is not None:
            self._unavailable_entity_config: _EntityConfig | None = _EntityConfig(
                display=self._unavailable_display,
                show_tabs=False,
                schedule_load=None,
            )
        else:
            self._unavailable_entity_config = None

        self._default_entity_config = self._settings_entity_config or _EntityConfig(
            display=self._file_display,
            show_tabs=True,
            schedule_load=self._schedule_load,
        )

        self._load_seq: int = 0
        self._tabs: ft.Tabs | None = None
        self._events_file_path: str | None = None
        self._spawns_file_path: str | None = None
        self._user_configured_entities: set[str] = set()
        self._show_unhandled_editors: bool = False
        self._profile_managed: set[str] = set()

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
            if os.path.exists(fpath):
                type_file_map[_get_label(fname)] = fpath
            else:
                logger.warning(
                    "Skipping type file %s: no such file", fpath
                )
        self._entities[TYPES_ENTITY] = type_file_map

        for fname, fpath in known_files.items():
            if fname not in type_files:
                entity = _get_entity(fname)
                label = _get_label(fname)
                self._entities[entity] = {label: fpath}

        for name, files in project.custom_entities.items():
            if files and name not in self._entities:
                self._entities[name] = files
        self._user_configured_entities = set(project.custom_entities)

        if project.profiles_dir and self._profile_service is not None:
            self._reload_profile_entities()

        self._add_expansion_entities(svc, economy_dir)

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
        if self._settings_display is not None:
            self._settings_display.clear()
        if self._form_display is not None:
            self._form_display.clear()
        if self._unavailable_display is not None:
            self._unavailable_display.clear()
        self._project = None
        self._entities = {}
        self._current_entity = None
        self._current_file = None
        self._profile_managed = set()
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

    def switch_entity(self, entity: str, *, force: bool = False) -> None:
        if (entity == self._current_entity and not force) or entity not in self._entities:
            return
        self._file_display.save_file()
        self._file_display.clear()
        self._event_display.clear()
        if self._settings_display is not None:
            self._settings_display.save_file()
            self._settings_display.clear()
        if self._form_display is not None:
            self._form_display.save_file()
            self._form_display.clear()
        self._clear_tabs()
        files = self._entities[entity]
        file_labels = list(files.keys())
        self._current_entity = entity

        config = self._config_for(entity)
        display = config.display
        if display is self._settings_display:
            self._settings_display.set_entity(entity)
        elif display is self._form_display:
            self._form_display.set_entity(entity)
            self._form_display.set_files(files)
            self._form_display.on_file_select = self.switch_file
            self._form_display.on_file_create = self._on_form_file_created
        elif self._unavailable_display is not None and display is self._unavailable_display:
            self._unavailable_display.set_entity(entity)

        self._content_slot.content = display.control
        if config.show_tabs:
            self._build_tabs(file_labels, config.show_add_tab)
            self._editor_stack.controls = [display.button_row, self._tabs, self._content_slot]
        else:
            self._editor_stack.controls = [display.button_row, self._content_slot]

        self._current_file = file_labels[0] if file_labels else None

        try:
            self.control.update()
        except RuntimeError:
            pass

        if config.schedule_load is not None:
            config.schedule_load()

    def switch_file(self, label: str) -> None:
        if self._current_entity is None or self._current_entity not in self._entities:
            return
        files = self._entities[self._current_entity]
        if label == self._current_file or label not in files:
            logger.info("SWITCH skip %s (current=%s)", label, self._current_file)
            return
        logger.info("SWITCH %s -> %s", self._current_file, label)
        config = self._config_for(self._current_entity)
        config.display.save_file()
        self._current_file = label
        if config.schedule_load is not None:
            config.schedule_load()

    def _on_form_file_created(self, label: str, path: str) -> None:
        if self._current_entity is None or self._current_entity not in self._entities:
            return
        self._entities[self._current_entity][label] = path
        self._current_file = label

    def save_file(self) -> None:
        self._file_display.save_file()
        self._event_display.save_file()
        if self._settings_display is not None:
            self._settings_display.save_file()
        if self._form_display is not None:
            self._form_display.save_file()

    def save_current(self, e: object = None) -> None:
        if self._current_entity is None:
            return
        config = self._config_for(self._current_entity)
        config.display.save_current(e)

    @property
    def project(self) -> Project | None:
        return self._project

    @property
    def file_display(self) -> FileDisplay:
        return self._file_display

    @property
    def event_display(self) -> EventDisplay:
        return self._event_display

    @property
    def settings_display(self) -> SettingsTableDisplay | None:
        return self._settings_display

    @property
    def form_display(self) -> FormDisplay | None:
        return self._form_display

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

    def _config_for(self, entity: str) -> _EntityConfig:
        if is_not_yet_available(entity) and self._unavailable_entity_config is not None:
            return self._unavailable_entity_config
        if entity in self._entity_configs:
            return self._entity_configs[entity]
        if self._unhandled_is_unavailable(entity):
            assert self._unavailable_entity_config is not None
            return self._unavailable_entity_config
        if (
            self._form_entity_config is not None
            and entity in self._entities
            and entity_has_form_schemas(entity, self._entities[entity])
        ):
            return self._form_entity_config
        return self._default_entity_config

    def _unhandled_is_unavailable(self, entity: str) -> bool:
        return (
            not self._show_unhandled_editors
            and self._unavailable_entity_config is not None
            and entity not in self._user_configured_entities
            and not is_registered_entity(entity)
        )

    def is_editable_entity(self, entity: str) -> bool:
        config = self._config_for(entity)
        return config.display is not self._unavailable_display

    def set_show_unhandled_editors(self, enabled: bool) -> None:
        if self._show_unhandled_editors == enabled:
            return
        self._show_unhandled_editors = enabled
        if self._project is not None:
            if self._project.profiles_dir:
                self._reload_profile_entities()
            if self._current_entity is not None:
                self.switch_entity(self._current_entity, force=True)

    def _add_expansion_entities(
        self, svc: EconomyService, economy_dir: str
    ) -> None:
        mission = svc.get_expansion_files(economy_dir)
        if not mission:
            return
        profile = self._entities.get("ExpansionMod", {})
        self._entities["ExpansionMod"] = {**mission, **profile}

    def _reload_profile_entities(self) -> None:
        if self._profile_service is None or self._project is None:
            return
        scanned = self._profile_service.scan_profiles(self._project.profiles_dir)
        managed: set[str] = set()
        for name, files in scanned.items():
            if name in self._user_configured_entities:
                continue
            if is_not_yet_available(name) or self._unhandled_is_unavailable(name):
                self._entities[name] = {}
                managed.add(name)
                continue
            if files:
                self._entities[name] = files
                managed.add(name)
        self._profile_managed = managed

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

    def _schedule_settings_load(self) -> None:
        self._load_seq += 1
        seq = self._load_seq
        logger.info("SCHEDULE_SETTINGS seq=%d file=%s", seq, self._current_file)
        try:
            self._page.run_task(self._load_current_file_async, seq)
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
        config = self._config_for(self._current_entity)
        display = config.display
        logger.info("LOADING seq=%d file=%s path=%s", seq, self._current_file, path)
        try:
            if display is self._settings_display and self._settings_display is not None:
                self._settings_display.set_entity(self._current_entity)
                await self._settings_display.load_file_async(
                    path, cancel_check=lambda: seq != self._load_seq
                )
            elif display is self._form_display and self._form_display is not None:
                self._form_display.set_entity(self._current_entity)
                self._form_display.set_files(files)
                await self._form_display.load_file_async(
                    path, cancel_check=lambda: seq != self._load_seq
                )
            else:
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
            self._file_display.button_row,
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
