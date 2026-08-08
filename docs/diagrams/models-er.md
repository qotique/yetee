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
        string project_name
    }

    Project {
        string connection_id
    }
    ConnectionConfig ||--o{ Project : "weak ref (connection_id)"
```

Notes / Пояснения:

- `RowData.values` keys correspond to the column names defined by
  `FieldDef.key` (`STATIC_FIELD_DEFS` in `src/models/field_def.py`).
- `UndoManager` stores `RowSnapshot`s (deep-copied values), not live `RowData`
  references.
- `Project.connection_id` is a weak string link to `ConnectionConfig.id` (used
  by remote projects). `Project.remote_dir` is the remote economy directory;
  `Project.is_remote` is true when `connection_id` is set.
- The `RowData ═ RowSnapshot` relation is implemented in
  `UndoManager.take_snapshot()`.

- `RowData.values` — ключи соответствуют именам колонок, заданным через
  `FieldDef.key` (`STATIC_FIELD_DEFS` в `src/models/field_def.py`).
- `UndoManager` хранит `RowSnapshot`-ы (deep-copy значений), не ссылки на
  живые `RowData`.
- `Project.connection_id` — слабая связь строкой на `ConnectionConfig.id`
  (используется remote-проектами). `Project.remote_dir` — удалённый каталог
  экономики; `Project.is_remote` истинно, когда задан `connection_id`.
- Связь `RowData ═ RowSnapshot` реализована в `UndoManager.take_snapshot()`.
