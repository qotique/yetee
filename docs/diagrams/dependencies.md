# Data flow & dependencies / Поток данных и зависимости

The diagram shows who builds whom (assembling) and the data flow from the entry
point down to the stores. All high-level entities are wired in the composition
root `src/di.py` (`create_app_services`).

Диаграмма показывает, кто кого создаёт (assembling) и поток данных от точки
входа до хранилищ. Все высокоуровневые сущности собираются в composition root
`src/di.py` (`create_app_services`).

> The remote-sync layer (`ConnectionManager`, `RemoteSyncService`, SSH/FTP) is
> still in development and not merged into `main` — shown with dashed lines.
>
> Слой remote-синхронизации (`ConnectionManager`, `RemoteSyncService`, SSH/FTP)
> находится в разработке и ещё не вмержен в `main` — показан пунктиром.

```mermaid
flowchart TB
    subgraph entry["Entry point"]
        main["App (src/main.py)"]
        di["di.create_app_services (composition root)"]
    end

    subgraph ui["UI"]
        ee["EconomyEditor (src/ui/economy_editor.py)"]
        fd["FileDisplay (src/file_display.py)"]
        evd["EventDisplay (src/event_display.py)"]
        dp["DetailPanel ✓ ui/detail_panel.py"]
        bp["BatchPanel ✓ ui/batch_panel.py"]
        cs["ChipSet ✓ ui/chip_set.py"]
    end

    subgraph controllers["Controllers"]
        tc["TableController"]
        sc["SearchController"]
        pag["PaginationController"]
        dirty["DirtyStateManager"]
        undo["UndoManager (src/models/undo_manager.py)"]
    end

    subgraph repo["Repositories"]
        xmlr["XmlRepository"]
        evr["EventRepository"]
        cache["FileCache"]
    end

    subgraph services["Services"]
        cfg["ConfigService"]
        econ["EconomyService"]
        prj["ProjectService"]
        stg["SettingsService"]
        upd["UpdateService"]
        ent["EntertainmentService"]
    end

    subgraph models["Models"]
        row["RowData"]
        fdef["FieldDef"]
        proj["Project"]
    end

    subgraph remote["Remote sync (WIP)"]
        cm["ConnectionManager"]
        cr["ConnectionRepository"]
        rss["RemoteSyncService"]
        conncfg["ConnectionConfig"]
        factory["connection_factory"]
        ssh["SSHConnection"]
        ftp["FTPConnection"]
    end

    main -->|"creates"| di
    di -->|"AppServices"| cfg
    di -->|"AppServices"| stg
    di -->|"AppServices"| upd
    di -->|"AppServices"| ent
    di -->|"AppServices"| prj
    di -->|"fixed FileCache"| cache
    di -->|"creates"| ee
    di -->|"creates (shared cache)"| fd
    di -->|"creates (shared cache)"| evd

    App._main -->|"swaps tabs"| ee
    ee -->|"load_project/unload"| fd
    ee -->|"load_project/unload"| evd
    ee -->|"config_service"| cfg

    fd -->|"xml_repo (IXmlRepository)"| xmlr
    fd -->|"cache (ICache)"| cache
    fd -->|"detail_panel (IDetailPanel)"| dp
    fd -->|"batch_panel (IBatchPanel)"| bp
    fd -->|"entertainment"| ent
    fd -->|"TableController"| tc
    fd -->|"UndoManager"| undo
    fd -->|"SearchController"| sc
    fd -->|"PaginationController"| pag
    fd -->|"DirtyStateManager"| dirty

    evd -->|"event_repo"| evr
    evd -->|"cache"| cache
    evd -->|"TableController"| tc
    evd -->|"UndoManager"| undo

    xmlr -->|"cache"| cache
    xmlr -->|"rows: RowData"| row
    evr -->|"cache"| cache
    evr -->|"rows: RowData"| row

    tc -->|"FieldDef/RowData"| models
    bp --> tc

    prj -->|"Project[]"| proj
    cfg -->|"ce: cfgeconomycore.xml"| xmlr
    econ -->|"types_dir/file list"| proj

    cm -->|"IRemoteConnection"| factory
    factory --> ssh
    factory --> ftp
    cm -->|"ConnectionConfig[]"| cr
    cm -->|"ConnectionConfig"| conncfg
    cr -->|"ConnectionConfig"| conncfg
    rss -->|"uses"| cm
    rss -->|"create()"| factory
```