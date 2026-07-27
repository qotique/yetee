from __future__ import annotations

from typing import TypedDict

import flet as ft

from controllers.dirty_state_manager import DirtyStateManager
from controllers.pagination_controller import PaginationController
from controllers.search_controller import SearchController
from controllers.table_controller import TableController
from file_display import FileDisplay
from repository.file_cache import FileCache
from repository.xml_repository import XmlRepository
from services.config_service import ConfigService
from services.entertainment_service import EntertainmentService
from services.settings_service import SettingsService
from services.update_service import UpdateService


class AppServices(TypedDict):
    config_service: ConfigService
    settings_service: SettingsService
    update_service: UpdateService
    entertainment_service: EntertainmentService
    cache: FileCache


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


def create_file_display(
    page: ft.Page,
    xml_repo: XmlRepository | None = None,
    cache: FileCache | None = None,
) -> FileDisplay:
    cache = cache or create_file_cache()
    xml_repo = xml_repo or create_xml_repository(cache)
    return FileDisplay(page=page, xml_repo=xml_repo, cache=cache)


def create_app_services(page: ft.Page) -> AppServices:
    return {
        "config_service": create_config_service(),
        "settings_service": create_settings_service(page),
        "update_service": create_update_service(page),
        "entertainment_service": create_entertainment_service(),
        "cache": create_file_cache(),
    }
