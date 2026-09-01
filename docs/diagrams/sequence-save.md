# Sequence: save + remote sync / Последовательность: сохранение + remote-синхронизация

All Save actions (top-level shell button, in-panel display buttons and the
MenuBar `File ▸ Save`, shortcut `Ctrl+S`) dispatch through the central
`CommandRegistry` (`save` command) to `EconomyEditor.save_current`, which
forwards to the active display. The display saves via `FileSession`/
`SaveCommand`, the repository and `FileCache`; after a successful save it fires
its `on_saved` callback exactly once, which the `App` facade wires to
`RemoteFlow.on_local_saved` so remote projects trigger a single upload
(remote-sync layer — `issue/25`). The old `App._on_save` — which called
`on_local_saved()` a second time — was removed.

Все кнопки Save (верхняя панель, кнопки в панели дисплея и меню
`File ▸ Save`, горячая клавиша `Ctrl+S`) диспетчеризуются через центральный
`CommandRegistry` (команда `save`) в `EconomyEditor.save_current`, который
проксирует вызов активному дисплею. Дисплей сохраняет через `FileSession`/
`SaveCommand`, репозиторий и `FileCache`; после успешного сохранения он
ровно один раз дёргает callback `on_saved`, который фасад `App` привязывает к
`RemoteFlow.on_local_saved`, чтобы для remote-проектов запустить единственную
выгрузку (слой remote-синхронизации — `issue/25`). Старый `App._on_save`,
вызывавший `on_local_saved()` второй раз, удалён.

```mermaid
sequenceDiagram
    autonumber
    participant B as Save button / MenuBar item (command "save")
    participant SR as CommandRegistry + AppCommand
    participant EE as EconomyEditor
    participant FD as FileDisplay
    participant FS as FileSession
    participant SC as SaveCommand
    participant D as DirtyStateManager
    participant R as XmlRepository
    participant C as FileCache
    participant A as App facade (main.py)
    participant RF as RemoteFlow (ui/remote_flow.py)
    participant RSS as RemoteSyncService
    participant CM as ConnectionManager
    participant F as IRemoteConnection (factory)

    B->>SR: on_click / on_click -> registry.execute("save")
    Note over SR: command.enabled ? (project opened)
    SR->>EE: EconomyEditor.save_current()
    EE->>FD: display.save_current()
    FD->>FS: save_current(e)
    FS->>SC: SaveCommand(repo, path, rows).execute()
    SC->>R: save(path, rows)
    R->>R: serialize rows -> XML
    R->>C: invalidate(path)
    R-->>SC: ok
    SC-->>FS: ok
    FD->>FS: mark_clean()
    FD->>A: on_saved()          (wired by App._wire_actions, exactly once)
    A->>RF: on_saved()
    alt remote project
        RF->>RSS: upload_to_remote(config, local_dir, remote_dir)
        RSS->>CM: create(config)
        CM->>F: create_connection(config, password)
        F-->>CM: IRemoteConnection
        RSS->>F: connect()          | if not connected
        RSS->>F: upload_file(local_path, remote_path)
        RSS->>F: disconnect()
    end
```