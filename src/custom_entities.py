from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from models.field_def import FieldDef, FieldType

RENDERER_XML: str = "xml"
RENDERER_JSON: str = "json"
RENDERER_TXT: str = "txt"
RENDERER_AUTO: str = ""

EXTENSION_RENDERERS: dict[str, str] = {
    ".xml": RENDERER_XML,
    ".json": RENDERER_JSON,
    ".txt": RENDERER_TXT,
}

_DEFAULT_RENDERER = RENDERER_TXT


@dataclass(frozen=True)
class FileConfig:
    renderer: str = RENDERER_AUTO
    columns: tuple[FieldDef, ...] = ()


@dataclass(frozen=True)
class EntityConfig:
    files: dict[str, FileConfig] = field(default_factory=dict)
    folders: dict[str, FileConfig] = field(default_factory=dict)
    default: FileConfig = FileConfig()

    def file_config(self, filename: str) -> FileConfig:
        name = Path(filename).name
        if name in self.files:
            return self.files[name]
        norm = filename.replace("\\", "/")
        for folder, cfg in self.folders.items():
            folder_norm = folder.replace("\\", "/").strip("/")
            if f"/{folder_norm}/" in f"/{norm}":
                return cfg
        return self.default


_DEFAULT_ENTITY = EntityConfig()

_CUSTOM_ENTITIES: dict[str, EntityConfig] = {}


def _field(key: str, label: str, width: int = 140) -> FieldDef:
    return FieldDef(
        key=key,
        label=label,
        type=FieldType.TEXT,
        width=width,
    )


def register_entity(entity: str, config: EntityConfig) -> None:
    _CUSTOM_ENTITIES[entity] = config


def is_registered_entity(entity: str) -> bool:
    return entity in _CUSTOM_ENTITIES


def get_entity_config(entity: str) -> EntityConfig:
    return _CUSTOM_ENTITIES.get(entity, _DEFAULT_ENTITY)


def get_renderer(entity: str, filename: str) -> str:
    config = get_entity_config(entity).file_config(filename)
    if config.renderer:
        return config.renderer
    suffix = Path(filename).suffix.lower()
    return EXTENSION_RENDERERS.get(suffix, _DEFAULT_RENDERER)


def get_columns(entity: str, filename: str) -> tuple[FieldDef, ...]:
    return get_entity_config(entity).file_config(filename).columns