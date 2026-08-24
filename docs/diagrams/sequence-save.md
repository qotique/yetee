# Sequence: save + remote sync / Последовательность: сохранение + remote-синхронизация

Local saving goes through `FileSession`/`SaveCommand`, the repository and
`FileCache`; after a successful save the display fires its `on_saved` callback,
so the `App` can trigger a remote upload (remote-sync layer — `issue/25`).

Локальное сохранение идёт через `FileSession`/`SaveCommand`, репозиторий и
`FileCache`; после успешного сохранения `FileDisplay` (или `EventDisplay`)
дёргает callback `on_saved`, чтобы `App` мог запустить выгрузку в remote
(слой remote-синхронизации — `issue/25`).

```mermaid
sequenceDiagram
    autonumber
    participant FD as FileDisplay
    participant FS as FileSession
    participant SC as SaveCommand
    participant D as DirtyStateManager
    participant R as XmlRepository
    participant C as FileCache
    participant A as App (main.py)
    participant RSS as RemoteSyncService
    participant CM as ConnectionManager
    participant F as IRemoteConnection (factory)

    FD->>FS: save_current(e)
    FS->>SC: SaveCommand(repo, path, rows).execute()
    SC->>R: save(path, rows)
    R->>R: serialize rows -> XML
    R->>C: invalidate(path)
    R-->>SC: ok
    SC-->>FS: ok
    FD->>FS: mark_clean()
    FD->>A: on_saved()          (only wired for remote App)
    alt remote project
        A->>RSS: upload_to_remote(config, local_dir, remote_dir)
        RSS->>CM: create(config)
        CM->>F: create_connection(config, password)
        F-->>CM: IRemoteConnection
        RSS->>F: connect()          | if not connected
        RSS->>F: upload_file(local_path, remote_path)
        RSS->>F: disconnect()
    end
```