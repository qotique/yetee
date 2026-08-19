from __future__ import annotations

import flet as ft

from custom_entities import EntityConfig, FileConfig, register_entity
from form_schema import (
    FormDict,
    FormField,
    FormGrid,
    FormSchema,
    register_form_folder_schema,
    register_form_schema,
)
from models.field_def import FieldDef, FieldType

RIGHT = ft.TextAlign.RIGHT
LEFT = ft.TextAlign.LEFT

TRADER_ICONS = [
    "Trader",
    "Fishing",
    "Medical",
    "Weapons",
    "Ammo",
    "Food",
    "Drink",
    "Meat",
    "Clothes",
    "Vehicles",
    "Explosives",
    "Containers",
    "Backpacks",
    "Parts",
    "Tools",
    "Building",
    "Seeds",
    "Farming",
    "Misc",
    "Money",
    "Hunting",
    "Deliver",
    "Questionmark",
]


def _field(
    key: str,
    label: str,
    ftype: FieldType = FieldType.TEXT,
    width: int = 140,
    options: list[str] | None = None,
) -> FieldDef:
    align = RIGHT if ftype in (FieldType.INT, FieldType.FLOAT) else LEFT
    return FieldDef(
        key=key,
        label=label,
        type=ftype,
        width=width,
        align=align,
        options=options,
    )


def _settings_config() -> dict[str, FileConfig]:
    return {
        "CoreSettings.json": FileConfig(
            columns=(
                _field("m_Version", "Version", FieldType.INT, 90),
                _field(
                    "ServerUpdateRateLimit",
                    "Server Update Rate Limit",
                    FieldType.INT,
                    200,
                ),
                _field(
                    "ForceExactCEItemLifetime",
                    "Force Exact CE Item Lifetime",
                    FieldType.INT,
                    220,
                ),
                _field(
                    "EnableInventoryCargoTidy",
                    "Enable Inventory Cargo Tidy",
                    FieldType.INT,
                    220,
                ),
            )
        ),
        "GeneralSettings.json": FileConfig(
            columns=(
                _field("m_Version", "Version", FieldType.INT, 90),
                _field(
                    "DisableShootToUnlock",
                    "Disable Shoot To Unlock",
                    FieldType.INT,
                    210,
                ),
                _field("EnableGravecross", "Enable Gravecross", FieldType.INT, 180),
                _field(
                    "EnableAIGravecross", "Enable AI Gravecross", FieldType.INT, 190
                ),
                _field("EnableLamps", "Enable Lamps", FieldType.INT, 150),
                _field("EnableGenerators", "Enable Generators", FieldType.INT, 170),
                _field("EnableLighthouses", "Enable Lighthouses", FieldType.INT, 175),
                _field("EnableAutoRun", "Enable Auto Run", FieldType.INT, 160),
                _field("UseDeathScreen", "Use Death Screen", FieldType.INT, 170),
                _field("EnableEarPlugs", "Enable Ear Plugs", FieldType.INT, 160),
            )
        ),
        "MissionSettings.json": FileConfig(
            columns=(
                _field("m_Version", "Version", FieldType.INT, 90),
                _field("Enabled", "Enabled", FieldType.INT, 110),
                _field(
                    "InitialMissionStartDelay",
                    "Initial Mission Start Delay",
                    FieldType.INT,
                    220,
                ),
                _field(
                    "TimeBetweenMissions", "Time Between Missions", FieldType.INT, 210
                ),
                _field("MinMissions", "Min Missions", FieldType.INT, 140),
                _field("MaxMissions", "Max Missions", FieldType.INT, 140),
                _field(
                    "MinPlayersToStartMissions",
                    "Min Players To Start Missions",
                    FieldType.INT,
                    230,
                ),
            )
        ),
    }


def _trader_columns() -> tuple[FieldDef, ...]:
    return (
        _field("m_Version", "Version", FieldType.INT, 90),
        _field("DisplayName", "Display Name", width=200),
        _field("MinRequiredReputation", "Min Reputation", FieldType.INT, 140),
        _field("MaxRequiredReputation", "Max Reputation", FieldType.INT, 140),
        _field("RequiredFaction", "Required Faction", width=180),
        _field("RequiredCompletedQuestID", "Required Quest ID", FieldType.INT, 170),
        _field("TraderIcon", "Trader Icon", FieldType.SINGLE_NAMED, 150, TRADER_ICONS),
        _field("DisplayCurrencyValue", "Display Currency Value", FieldType.INT, 210),
        _field("DisplayCurrencyName", "Display Currency Name", width=200),
        _field("UseCategoryOrder", "Use Category Order", FieldType.INT, 180),
    )


def _category_columns() -> tuple[FieldDef, ...]:
    return (
        _field("m_Version", "Version", FieldType.INT, 90),
        _field("DisplayName", "Display Name", width=200),
        _field("Icon", "Icon", FieldType.SINGLE_NAMED, 140, TRADER_ICONS),
        _field("Color", "Color", width=120),
        _field("InitStockPercent", "Init Stock Percent", FieldType.FLOAT, 170),
        _field("IsExchange", "Is Exchange", FieldType.INT, 130),
    )


def _ai_settings_columns() -> tuple[FieldDef, ...]:
    return (
        _field("m_Version", "Version", FieldType.INT, 90),
        _field("AccuracyMin", "Accuracy Min", FieldType.FLOAT, 140),
        _field("AccuracyMax", "Accuracy Max", FieldType.FLOAT, 140),
        _field("ThreatDistanceLimit", "Threat Distance Limit", FieldType.FLOAT, 200),
        _field("DamageMultiplier", "Damage Multiplier", FieldType.FLOAT, 170),
        _field(
            "DamageReceivedMultiplier",
            "Damage Received Multiplier",
            FieldType.FLOAT,
            220,
        ),
        _field("Vaulting", "Vaulting", FieldType.INT, 110),
        _field("MaxRecruitableAI", "Max Recruitable AI", FieldType.INT, 170),
        _field("CanRecruitFriendly", "Can Recruit Friendly", FieldType.INT, 180),
        _field("CanRecruitGuards", "Can Recruit Guards", FieldType.INT, 175),
    )


def _quest_settings_columns() -> tuple[FieldDef, ...]:
    return (
        _field("m_Version", "Version", FieldType.INT, 90),
        _field("EnableQuests", "Enable Quests", FieldType.INT, 150),
        _field("EnableQuestLogTab", "Enable Quest Log Tab", FieldType.INT, 190),
        _field("CreateQuestNPCMarkers", "Create Quest NPC Markers", FieldType.INT, 220),
        _field("GroupQuestMode", "Group Quest Mode", FieldType.INT, 170),
        _field("WeeklyResetHour", "Weekly Reset Hour", FieldType.INT, 170),
        _field("WeeklyResetMinute", "Weekly Reset Minute", FieldType.INT, 180),
        _field("DailyResetHour", "Daily Reset Hour", FieldType.INT, 165),
        _field("DailyResetMinute", "Daily Reset Minute", FieldType.INT, 175),
        _field("UseUTCTime", "Use UTC Time", FieldType.INT, 140),
        _field("MaxActiveQuests", "Max Active Quests", FieldType.INT, 170),
    )


_PROFILE_SETTINGS = _settings_config()
_MISSION_SETTINGS = _settings_config()

register_entity(
    "ExpansionMod",
    EntityConfig(files=_PROFILE_SETTINGS),
)

register_entity(
    "Expansion Settings",
    EntityConfig(files=_MISSION_SETTINGS),
)

register_entity(
    "Expansion Market",
    EntityConfig(
        folders={
            "market/traders": FileConfig(columns=_trader_columns()),
            "market/categories": FileConfig(columns=_category_columns()),
        },
        default=FileConfig(columns=_trader_columns()),
    ),
)

register_entity(
    "Expansion Quests",
    EntityConfig(
        files={
            "QuestSettings.json": FileConfig(columns=_quest_settings_columns()),
        }
    ),
)

register_entity(
    "Expansion AI",
    EntityConfig(
        folders={
            "ai/settings": FileConfig(columns=_ai_settings_columns()),
        }
    ),
)


def _to_field(fd: FieldDef) -> FormField:
    return FormField(
        key=fd.key,
        label=fd.label,
        type=fd.type,
        options=tuple(fd.options or ()),
    )


def _form_fields(columns: tuple[FieldDef, ...]) -> tuple[FormField, ...]:
    return tuple(_to_field(fd) for fd in columns)


def _settings_schema(columns: tuple[FieldDef, ...]) -> FormSchema:
    return FormSchema(fields=_form_fields(columns))


_SETTINGS_SCHEMA = _settings_schema(())
_SETTINGS_FILES = {
    "CoreSettings.json",
    "GeneralSettings.json",
    "MissionSettings.json",
}


def _register_settings_schemas() -> None:
    per_file = {
        "CoreSettings.json": _settings_schema(
            _settings_config()["CoreSettings.json"].columns
        ),
        "GeneralSettings.json": _settings_schema(
            _settings_config()["GeneralSettings.json"].columns
        ),
        "MissionSettings.json": _settings_schema(
            _settings_config()["MissionSettings.json"].columns
        ),
    }
    for entity in ("ExpansionMod", "Expansion Settings"):
        for filename, schema in per_file.items():
            register_form_schema(entity, filename, schema)


def _register_market_schemas() -> None:
    trader_schema = FormSchema(
        fields=_form_fields(_trader_columns()),
        dicts=(
            FormDict(
                key="Items",
                label="Items",
                value_type=FieldType.INT,
            ),
        ),
        name_key="DisplayName",
    )
    category_schema = FormSchema(
        fields=_form_fields(_category_columns()),
        grids=(
            FormGrid(
                key="Items",
                label="Items",
                columns=(
                    FormField("ClassName", "Class Name"),
                    FormField("MaxPriceThreshold", "Max Price", FieldType.INT),
                    FormField("MinPriceThreshold", "Min Price", FieldType.INT),
                    FormField("SellPricePercent", "Sell Price %", FieldType.FLOAT),
                    FormField("MaxStockThreshold", "Max Stock", FieldType.INT),
                    FormField("MinStockThreshold", "Min Stock", FieldType.INT),
                    FormField("QuantityPercent", "Quantity %", FieldType.INT),
                ),
            ),
        ),
        name_key="DisplayName",
    )
    register_form_folder_schema("Expansion Market", "market/traders", trader_schema)
    register_form_folder_schema(
        "Expansion Market", "market/categories", category_schema
    )
    register_form_folder_schema("ExpansionMod", "market/traders", trader_schema)
    register_form_folder_schema("ExpansionMod", "market/categories", category_schema)


def _register_quest_schemas() -> None:
    register_form_schema(
        "Expansion Quests",
        "QuestSettings.json",
        _settings_schema(_quest_settings_columns()),
    )
    register_form_schema(
        "ExpansionMod",
        "QuestSettings.json",
        _settings_schema(_quest_settings_columns()),
    )


def _register_ai_schemas() -> None:
    register_form_folder_schema(
        "Expansion AI",
        "ai/settings",
        _settings_schema(_ai_settings_columns()),
    )
    register_form_folder_schema(
        "ExpansionMod",
        "ai/settings",
        _settings_schema(_ai_settings_columns()),
    )


_register_settings_schemas()
_register_market_schemas()
_register_quest_schemas()
_register_ai_schemas()
