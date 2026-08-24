from __future__ import annotations

from models.custom_entities import RENDERER_TXT

DEFAULT_MESSAGE = (
    "Editing for this mod is not available yet. Planned in a future version."
)


class NotYetAvailableMod:
    name: str = ""
    message: str = DEFAULT_MESSAGE

    def get_renderer(self, filename: str) -> str:
        del filename
        return RENDERER_TXT


class TraderX(NotYetAvailableMod):
    name = "TraderX"


class CommunityOnlineTools(NotYetAvailableMod):
    name = "CommunityOnlineTools"


class PermissionsFramework(NotYetAvailableMod):
    name = "PermissionsFramework"


class SpawnerBubaku(NotYetAvailableMod):
    name = "SpawnerBubaku"


class AS_Mods(NotYetAvailableMod):
    name = "AS_Mods"


_HANDLERS: dict[str, NotYetAvailableMod] = {
    handler.name: handler()
    for handler in (
        TraderX,
        CommunityOnlineTools,
        PermissionsFramework,
        SpawnerBubaku,
        AS_Mods,
    )
}


def get_mod_handler(entity: str) -> NotYetAvailableMod | None:
    return _HANDLERS.get(entity)


def is_not_yet_available(entity: str) -> bool:
    return entity in _HANDLERS


def not_yet_available_entities() -> set[str]:
    return set(_HANDLERS)
