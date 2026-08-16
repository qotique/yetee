from __future__ import annotations

from custom_entities import (
    EXTENSION_RENDERERS,
    RENDERER_JSON,
    RENDERER_TXT,
    RENDERER_XML,
    EntityConfig,
    FileConfig,
    get_columns,
    get_renderer,
    is_registered_entity,
    register_entity,
)
from models.field_def import FieldDef, FieldType


def test_is_registered_entity_true_after_register():
    assert not is_registered_entity("MyMod")
    register_entity("MyMod", EntityConfig())
    assert is_registered_entity("MyMod")


def test_is_registered_entity_false_by_default():
    assert not is_registered_entity("UnknownMod")


def test_extension_renderers_for_known_extensions():
    assert EXTENSION_RENDERERS[".xml"] == RENDERER_XML
    assert EXTENSION_RENDERERS[".json"] == RENDERER_JSON
    assert EXTENSION_RENDERERS[".txt"] == RENDERER_TXT


def test_get_renderer_defaults_by_extension():
    assert get_renderer("AnyEntity", "cfg.json") == RENDERER_JSON
    assert get_renderer("AnyEntity", "settings.xml") == RENDERER_XML
    assert get_renderer("AnyEntity", "log.txt") == RENDERER_TXT


def test_get_renderer_unknown_extension_falls_back_to_txt():
    assert get_renderer("AnyEntity", "file.ini") == RENDERER_TXT


def test_get_renderer_types_entity_has_no_schema():
    assert get_renderer("Types", "types.xml") == RENDERER_XML


def test_schema_can_override_renderer():
    register_entity(
        "MyMod", EntityConfig(files={"raw.txt": FileConfig(renderer=RENDERER_JSON)})
    )
    assert get_renderer("MyMod", "raw.txt") == RENDERER_JSON


def test_schema_can_override_renderer_per_file():
    register_entity(
        "MyMod2",
        EntityConfig(
            files={
                "a.txt": FileConfig(renderer=RENDERER_XML),
                "b.txt": FileConfig(renderer=RENDERER_JSON),
            }
        ),
    )
    assert get_renderer("MyMod2", "a.txt") == RENDERER_XML
    assert get_renderer("MyMod2", "b.txt") == RENDERER_JSON


def test_get_columns_empty_by_default():
    assert get_columns("Plain", "a.xml") == ()


def test_get_columns_declared_in_schema():
    cols = (
        FieldDef("name", "Name", FieldType.TEXT, width=120),
        FieldDef("value", "Value", FieldType.TEXT, width=200),
    )
    register_entity("Declared", EntityConfig(files={"s.xml": FileConfig(columns=cols)}))
    assert get_columns("Declared", "s.xml") == cols


def test_get_columns_ignores_other_files():
    register_entity(
        "Declared2",
        EntityConfig(
            files={"s.xml": FileConfig(columns=(FieldDef("k", "K", FieldType.TEXT),))}
        ),
    )
    assert get_columns("Declared2", "other.txt") == ()


def test_register_entity_then_get_renderer():
    register_entity(
        "Registered",
        EntityConfig(files={"x.json": FileConfig(renderer=RENDERER_TXT)}),
    )
    assert get_renderer("Registered", "x.json") == RENDERER_TXT
