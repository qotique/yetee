# Sequence: file load / Последовательность: загрузка файла

The flow of opening a types/events file. `FileDisplay` and `EventDisplay` kick
off background loading themselves through the shared cache and reusable
controllers.

Поток открытия types/events файла. `FileDisplay` и `EventDisplay` сами
запускают фоновую загрузку через общий кэш и переиспользуемые контроллеры.

```mermaid
sequenceDiagram
    autonumber
    participant EE as EconomyEditor
    participant FD as FileDisplay
    participant TBC as TableController
    participant UM as UndoManager
    participant S as SearchController
    participant P as PaginationController
    participant D as DirtyStateManager
    participant R as XmlRepository
    participant C as FileCache

    EE->>FD: load_project(project)
    FD->>FD: schedule_load()
    FD->>FD: _load_current_file_async()

    FD->>R: parse_file_async(path)
    R->>C: get_rows(path)
    alt cache miss
        C-->>R: None
        R->>R: parse XML (lxml) -> list[RowData]
        R->>C: set_rows(path, rows)
    end
    R-->>FD: rows

    FD->>UM: take_snapshot(rows)
    FD->>P: page_index / page_size
    FD->>S: filter_rows(rows)
    FD->>TBC: render(rows, filtered, page_idx)

    TBC-->>FD: UI (table) ready / готов
    D->>D: mark_clean()
```

Differences for events (`EventDisplay`): same flow, but `XmlRepository` is
replaced by `EventRepository` (parses `cfgeventspawns.xml` → `RowData`), and
`TableController`/`UndoManager` are reused.

Отличия для событий (`EventDisplay`): тот же поток, но `XmlRepository`
заменяется на `EventRepository` (парсинг `cfgeventspawns.xml` → `RowData`),
а `TableController`/`UndoManager` переиспользуются.