# Data models ER / ER-диаграмма моделей данных

Relations between dataclass models. The models are primarily data snapshots:
`RowData` is a table row (types/events), `RowSnapshot` is its undo snapshot.

Связи между dataclass-моделями. Модели — это прежде всего снимки данных:
`RowData` — строка таблицы (types/events), `RowSnapshot` — её снимок для undo.

> `ConnectionConfig` and the remote-project model belong to the remote-sync layer
> (`issue/25`: SSH/FTP connections).
>
> `ConnectionConfig` и проектная модель remote-проекта относятся к слою
> remote-синхронизации (`issue/25`: SSH/FTP подключения).

```mermaid
erDiagram
    Project ||--o{ TypeFile : "types_dir"
    Project {
        string name
        string economy_dir
        string types_dir
        string profiles_dir
        dict custom_entities
        float created_at
        float last_opened
        string connection_id
        string remote_dir
    }

    TypeFile ||--o{ RowData : "parses rows"
    TypeFile {
        string path
    }

    RowData ||--o{ RowSnapshot : "snapshot (undo)"
    RowData {
        dict values
        dict flags
        Element elem
    }

    RowSnapshot {
        dict values
        dict flags
        Element elem
    }

    FieldDef ||--|| RowData : "defines keys of values"
    FieldDef {
        string key
        string label
        FieldType type
        int width
        list options
    }

    EconomyService ||--|| Project : "loads project"
    EconomyService {
        string economy_dir
    }

    ProfileService ||--|| Project : "scans profiles_dir"
    ProfileService {
        string profiles_dir
    }

    ConnectionManager ||--o{ ConnectionConfig : "active + list"
    ConnectionManager {
        string active_id
    }

    ConnectionConfig {
        string id
        string protocol
        string host
        int port
        string username
        string key_path
        string remote_economy_dir
        string remote_profiles_dir
        string project_name
    }

    Project {
        string connection_id
    }
    ConnectionConfig ||--o{ Project : "weak ref (connection_id)"

    ProfilePreloadService ||--|| PreloadEstimate
    PreloadEstimate {
        int count
        int total_bytes
        float seconds
    }
```

Notes / Пояснения:

- `RowData.values` keys correspond to the column names defined by
  `FieldDef.key` (`STATIC_FIELD_DEFS` in `src/models/field_def.py`).
- `UndoManager` stores `RowSnapshot`s (deep-copied values), not live `RowData`
  references.
- `Project.connection_id` is a weak string link to `ConnectionConfig.id` (used
  by remote projects). `Project.remote_dir` is the remote economy directory;
  `Project.is_remote` is true when `connection_id` is set.
- `Project.custom_entities` holds user-defined entities
  `{entity_name: {file_label: absolute_path}}`, merged before profile scan
  results (custom overrides dynamic profile entities, but never the built-in
  Types/Events/Globals ones).
- `ProfileService.scan_profiles(profiles_dir)` turns each first-level directory
  into an entity, collecting `.xml/.json/.txt` files recursively from it.
- Custom entity files are rendered by `SettingsTableDisplay` (generic settings
  table for XML/JSON + raw text for TXT). Renderer and optional columns are
  declared per file in `src/custom_entities.py`; when no columns are declared,
  they are auto-detected from the XML/JSON structure. `ConnectionConfig.remote_profiles_dir`
  makes the profiles tree part of SSH/FTP sync (downloaded to the local
  `~/.yetee/workspace/<id>/profiles` and uploaded back on save).
- The `RowData ═ RowSnapshot` relation is implemented in
  `UndoManager.take_snapshot()`.
- `PreloadEstimate` is produced by `ProfilePreloadService.estimate_preload`
  (byte-throughput model) to estimate how long loading all profile files will
  take; `App` shows a confirm dialog with a progress bar when the count is at
  least `PROFILE_PRELOAD_DIALOG_MIN_FILES`.
- `NotYetAvailableMod` subclasses in `src/mod_handlers.py` (TraderX,
  CommunityOnlineTools, PermissionsFramework, SpawnerBubaku, AS_Mods) mark
  entity directories that are skipped during loading and render a notice via
  `UnavailableDisplay` instead of an editable table.

- `RowData.values` — ключи соответствуют именам колонок, заданным через
  `FieldDef.key` (`STATIC_FIELD_DEFS` в `src/models/field_def.py`).
- `UndoManager` хранит `RowSnapshot`-ы (deep-copy значений), не ссылки на
  живые `RowData`.
- `Project.connection_id` — слабая связь строкой на `ConnectionConfig.id`
  (используется remote-проектами). `Project.remote_dir` — удалённый каталог
  экономики; `Project.is_remote` истинно, когда задан `connection_id`.
- Связь `RowData ═ RowSnapshot` реализована в `UndoManager.take_snapshot()`.
- `PreloadEstimate` формируется `ProfilePreloadService.estimate_preload`
  (модель пропускной способности) для оценки времени загрузки всех profile-файлов;
  `App` показывает диалог подтверждения с прогресс-баром, когда количество
  файлов не меньше `PROFILE_PRELOAD_DIALOG_MIN_FILES`.
- Подклассы `NotYetAvailableMod` в `src/mod_handlers.py` (TraderX,
  CommunityOnlineTools, PermissionsFramework, SpawnerBubaku, AS_Mods) помечают
  каталоги сущностей, которые пропускаются при загрузке и вместо таблицы
  показывают уведомление через `UnavailableDisplay`.
- Файлы кастомных сущностей рендерятся `SettingsTableDisplay` (обобщённая
  таблица настроек для XML/JSON + сырой текст для TXT). Рендерер и опциональные
  колонки объявляются в `src/custom_entities.py`; без объявления колонки
  определяются автоматически по структуре XML/JSON. `ConnectionConfig.remote_profiles_dir`
  включает дерево profiles в SSH/FTP синхронизацию (скачивается в локальный
  `~/.yetee/workspace/<id>/profiles` и загружается обратно при сохранении).
