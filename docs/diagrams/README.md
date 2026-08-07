# Architecture Diagrams / Диаграммы архитектуры

A set of diagrams to help navigate the codebase. `.md` files contain
[Mermaid](https://mermaid.js.org) diagrams and render on GitHub/README with no
extra tools. `.puml` files are [PlantUML](https://plantuml.com) class diagrams
(manually written/edited).

Набор диаграмм для навигации по кодовой базе. Файлы `.md` содержат
диаграммы в формате [Mermaid](https://mermaid.js.org) и рендерятся на
GitHub/README без дополнительных инструментов. Файлы `.puml` — диаграммы
классов в формате [PlantUML](https://plantuml.com) (генерируются/правятся
вручную).

## Contents / Содержание

| Diagram / Диаграмма | File / Файл | Description / Описание |
|---|---|---|
| Data flow & dependencies / Поток данных и зависимости | [dependencies.md](dependencies.md) | Who builds whom: App → DI → EconomyEditor → FileDisplay/EventDisplay → controllers/services/repositories |
| Data models ER / ER-модели данных | [models-er.md](models-er.md) | Relations between dataclass models (RowData, FieldDef, Project, ConnectionConfig) |
| Sequence: file load / Загрузка файла | [sequence-load.md](sequence-load.md) | `EconomyEditor → FileDisplay → XmlRepository → FileCache` flow |
| Sequence: save + remote / Сохранение + remote | [sequence-save.md](sequence-save.md) | `save → RemoteSyncService.upload_to_remote` flow |
| Class: controllers / Контроллеры | [class-controllers.puml](class-controllers.puml) | TableController, SearchController, PaginationController, DirtyStateManager, UndoManager |
| Class: services & protocols / Сервисы и протоколы | [class-services.puml](class-services.puml) | Services implementing Protocol interfaces from `src/protocols.py` |
| Class: remote transports / Remote-транспорты | [class-transports.puml](class-transports.puml) | IRemoteConnection → SSH/FTP, factory, ConnectionManager |
| Class: models / Модели | [class-models.puml](class-models.puml) | Dataclass models and their relations |

## Regenerating class diagrams / Автогенерация class-диаграмм

Class diagrams can be regenerated from the code with `pyreverse` (bundled with
`pylint`): Диаграммы классов можно перегенерировать из кода через `pyreverse`
(входит в `pylint`):

```bash
uv run python scripts/generate_diagrams.py
```

Generated files land in `docs/diagrams/generated/`. The hand-written `.puml`
files in this folder are simplified, navigation-friendly versions; when the
architecture changes, update them and/or re-run `pyreverse`.

Сгенерированные файлы кладутся в `docs/diagrams/generated/`. Ручные
`.puml`-файлы в этой папке — упрощённые и пригодные для навигации версии;
при изменении архитектуры обновите их и/или перезапустите `pyreverse`.

## Change rule / Правило для изменений

If you change the architecture (layers, DI factories, models, controllers),
keep the relevant diagrams in this PR up to date. See also `AGENTS.md`.

Если вы меняете архитектуру (слои, DI-фабрики, модели, контроллеры) —
актуализируйте соответствующие диаграммы в этом PR. См. также `AGENTS.md`.