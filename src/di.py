from __future__ import annotations

from typing import TypedDict

import flet as ft

from controllers.dirty_state_manager import DirtyStateManager
from controllers.pagination_controller import PaginationController
from controllers.search_controller import SearchController
from controllers.table_controller import TableController
from event_display import EventDisplay
from file_display import FileDisplay
from repository.event_repository import EventRepository
from repository.file_cache import FileCache
from repository.xml_repository import XmlRepository
from services.config_service import ConfigService
from services.entertainment_service import EntertainmentService
from services.project_service import ProjectService
from services.settings_service import SettingsService
from services.update_service import UpdateService
from ui.economy_editor import EconomyEditor


class AppServices(TypedDict):
    config_service: ConfigService
    settings_service: SettingsService
    update_service: UpdateService
    entertainment_service: EntertainmentService
    cache: FileCache
    economy_editor: EconomyEditor
    project_service: ProjectService


def create_file_cache() -> FileCache:
    return FileCache()


def create_xml_repository(cache: FileCache | None = None) -> XmlRepository:
    return XmlRepository(cache=cache or create_file_cache())


def create_config_service() -> ConfigService:
    return ConfigService()


def create_settings_service(page: ft.Page) -> SettingsService:
    return SettingsService(page)


def create_update_service(page: ft.Page) -> UpdateService:
    return UpdateService(page)


def create_entertainment_service() -> EntertainmentService:
    return EntertainmentService()


def create_table_controller(page: ft.Page) -> TableController:
    return TableController(page)


def create_pagination_controller(page_size: int = 50) -> PaginationController:
    return PaginationController(page_size)


def create_search_controller() -> SearchController:
    return SearchController()


def create_dirty_state_manager() -> DirtyStateManager:
    return DirtyStateManager()


def create_event_repository(cache: FileCache | None = None) -> EventRepository:
    return EventRepository(cache=cache or create_file_cache())


def create_event_display(
    page: ft.Page,
    event_repo: EventRepository | None = None,
    cache: FileCache | None = None,
    entertainment_service: EntertainmentService | None = None,
) -> EventDisplay:
    cache = cache or create_file_cache()
    event_repo = event_repo or create_event_repository(cache)
    return EventDisplay(
        page=page,
        event_repo=event_repo,
        cache=cache,
        entertainment_service=entertainment_service,
    )


def create_file_display(
    page: ft.Page,
    xml_repo: XmlRepository | None = None,
    cache: FileCache | None = None,
    entertainment_service: EntertainmentService | None = None,
) -> FileDisplay:
    cache = cache or create_file_cache()
    xml_repo = xml_repo or create_xml_repository(cache)
    return FileDisplay(
        page=page,
        xml_repo=xml_repo,
        cache=cache,
        entertainment_service=entertainment_service,
    )


def create_economy_editor(
    page: ft.Page,
    config_service: ConfigService | None = None,
    entertainment_service: EntertainmentService | None = None,
    cache: FileCache | None = None,
    file_display: FileDisplay | None = None,
    event_display: EventDisplay | None = None,
) -> EconomyEditor:
    cache = cache or create_file_cache()
    file_display = file_display or create_file_display(
        page=page,
        cache=cache,
        entertainment_service=entertainment_service,
    )
    event_display = event_display or create_event_display(
        page=page,
        cache=cache,
        entertainment_service=entertainment_service,
    )
    return EconomyEditor(
        page=page,
        file_display=file_display,
        event_display=event_display,
        config_service=config_service,
    )


def create_app_services(page: ft.Page) -> AppServices:
    cache = create_file_cache()
    config_service = create_config_service()
    entertainment_service = create_entertainment_service()
    return {
        "config_service": config_service,
        "settings_service": create_settings_service(page),
        "update_service": create_update_service(page),
        "entertainment_service": entertainment_service,
        "cache": cache,
        "economy_editor": create_economy_editor(
            page=page,
            config_service=config_service,
            entertainment_service=entertainment_service,
            cache=cache,
        ),
        "project_service": ProjectService(),
    }
