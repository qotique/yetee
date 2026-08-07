# Sequence: save + remote sync / Последовательность: сохранение + remote-синхронизация

Local saving goes through the repository and `FileCache`; optionally an upload
to the remote is triggered after saving (remote-sync layer — WIP).

Локальное сохранение идёт через репозиторий и `FileCache`; опционально после
сохранения запускается выгрузка в remote (слой remote-синхронизации — WIP).

```mermaid
sequenceDiagram
    autonumber
    participant FD as FileDisplay
    participant D as DirtyStateManager
    participant R as XmlRepository
    participant C as FileCache
    participant RSS as RemoteSyncService
    participant CM as ConnectionManager
    participant F as IRemoteConnection (factory)

    FD->>D: is_dirty?
    alt dirty
        FD->>R: save_async(path, rows)
        R->>R: serialize rows -> XML
        R->>C: invalidate(path)
        R-->>FD: ok
        FD->>D: mark_clean()
    end

    alt remote enabled (WIP)
        FD->>RSS: upload_to_remote(config, local_dir, remote_dir)
        RSS->>CM: create(config)
        CM->>F: create_connection(config, password)
        F-->>CM: IRemoteConnection
        RSS->>F: connect()          | if not connected
        RSS->>F: upload_file(local_path, remote_path)
        RSS->>F: disconnect()
    end
```

> The `RemoteSyncService`/`ConnectionManager`/SSH/FTP part is not yet on `main`
> — shown as the target behavior (see `docs/diagrams/dependencies.md`).
>
> Часть с `RemoteSyncService`/`ConnectionManager`/SSH/FTP ещё не в
> `main` — показана как целевое поведение (см. `docs/diagrams/dependencies.md`).