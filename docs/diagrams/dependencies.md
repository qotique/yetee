# Data flow & dependencies / Поток данных и зависимости

The diagram shows who builds whom (assembling) and the data flow from the entry
point down to the stores. All high-level entities are wired in the composition
root `src/core/di.py` (`create_app_services`). The `App` class is a thin facade:
it wires `AppShell` (view), `ProjectFlow` / `RemoteFlow` (presentation flows)
and `SettingsManager` (flet-free settings state).

Диаграмма показывает, кто кого создаёт (assembling) и поток данных от точки
входа до хранилищ. Все высокоуровневые сущности собираются в composition root
`src/core/di.py` (`create_app_services`). Класс `App` — тонкий фасад: он
связывает `AppShell` (представление), `ProjectFlow` / `RemoteFlow`
(презентационные потоки) и `SettingsManager` (состояние настроек без flet).

> The remote-sync layer (`ConnectionManager`, `RemoteSyncService`, SSH/FTP) is
> part of the `issue/25` branch (SSH/FTP connections).
>
> Слой remote-синхронизации (`ConnectionManager`, `RemoteSyncService`, SSH/FTP)
> находится в ветке `issue/25` (SSH/FTP подключения).

```mermaid
flowchart TB
    subgraph entry["Entry point"]
        main["App facade (src/main.py)"]
        di["di.create_app_services (composition root)"]
    end

    subgraph ui["UI"]
        shell["AppShell (src/ui/app_shell.py)"]
        pflow["ProjectFlow (src/ui/project_flow.py)"]
        rflow["RemoteFlow (src/ui/remote_flow.py)"]
        dlg["ui/dialogs.py (show_error/show_message)"]
        mb["CommandMenuBar (src/ui/menu_bar.py)"]
        ee["EconomyEditor (src/ui/economy_editor.py)"]
        fd["FileDisplay (src/ui/file_display.py)"]
        evd["EventDisplay (src/ui/event_display.py)"]
        std["SettingsTableDisplay (src/ui/settings_table_display.py)"]
        fmd["FormDisplay (src/ui/form_display.py)"]
        uav["UnavailableDisplay (src/ui/unavailable_display.py)"]
        dp["DetailPanel ✓ ui/detail_panel.py"]
        bp["BatchPanel ✓ ui/batch_panel.py"]
        cs["ChipSet ✓ ui/chip_set.py"]
        fm["FilterMenu ✓ ui/filter_menu.py (FilterSpec)"]
        fp["FunPresenter ✓ ui/fun_presenter.py"]
    end

    subgraph cmds["Commands"]
        creg["CommandRegistry (src/commands/registry.py)"]
        appcmd["AppCommand (src/commands/registry.py)"]
        iproto["IAppCommand protocol (src/commands/protocols.py)"]
        cmd["commands.py (RandomizeCommand / SaveCommand)"]
    end

    subgraph controllers["Controllers"]
        sm["SettingsManager (src/controllers/settings_manager.py, flet-free)"]
        fs["FileSession (src/controllers/file_session.py, flet-free)"]
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
        sxmlr["XmlSettingsRepository"]
        sjsonr["JsonSettingsRepository"]
    end

    subgraph services["Services"]
        cfg["ConfigService"]
        econ["EconomyService"]
        prj["ProjectService"]
        stg["SettingsService"]
        upd["UpdateService"]
        ent["EntertainmentService"]
        prof["ProfileService"]
        pload["ProfilePreloadService (src/services/profile_preload_service.py)"]
    end

    subgraph schema["Schema (code module)"]
        cent["src/models/custom_entities.py"]
        exp["src/models/expansion.py (Expansion Mod entities)"]
        fschema["src/models/form_schema.py (FormSchema tree + registry)"]
        modh["src/models/mod_handlers.py (NotYetAvailableMod registry)"]
    end

    subgraph models["Models"]
        row["RowData"]
        fdef["FieldDef"]
        proj["Project"]
    end

    subgraph remote["Remote sync"]
        cm["ConnectionManager"]
        cr["ConnectionRepository"]
        rss["RemoteSyncService"]
        conncfg["ConnectionConfig"]
        factory["connection_factory"]
        ssh["SSHConnection"]
        ftp["FTPConnection"]
    end

    main -->|"creates"| di
    main -->|"creates + wires"| shell
    main -->|"creates"| pflow
    main -->|"creates"| rflow
    main -->|"creates"| sm
    main -->|"register commands (AppCommand)"| creg
    main -->|"builds + attaches via shell.attach_menu_bar"| mb
    mb -->|"Observer: subscribe(refresh) + execute(id)"| creg
    shell -->|"widgets + view ops"| main
    shell -->|"_commands.refresh()"| creg
    pflow -->|"project dialogs, selectors, preload"| ee
    pflow -->|"dropdowns/visibility/cat icons"| shell
    pflow -->|"projects CRUD"| prj
    pflow -->|"scan_profiles"| prof
    rflow -->|"open remote / refresh / upload-on-save"| rss
    rflow -->|"connections add/test/delete"| cm
    rflow -->|"reload/open project"| pflow
    rflow --> dlg
    sm -->|"load/save settings"| stg
    sm -->|"fun flags"| ent
    di -->|"AppServices"| cfg
    di -->|"AppServices"| stg
    di -->|"AppServices"| upd
    di -->|"AppServices"| ent
    di -->|"AppServices"| prj
    di -->|"fixed FileCache"| cache
    di -->|"creates"| cm
    di -->|"creates"| rss
    di -->|"creates"| ee
    di -->|"creates"| prof
    di -->|"creates + threads into displays"| creg
    di -->|"creates (shared cache)"| fd
    di -->|"creates (shared cache)"| evd
    di -->|"creates"| std
    di -->|"creates"| fmd
    di -->|"creates"| uav

    App._main -->|"swaps tabs"| ee
    ee -->|"load_project/unload"| fd
    ee -->|"load_project/unload"| evd
    ee -->|"load_project/custom entities"| std
    ee -->|"load_project/expansion areas"| std
    ee -->|"load_project/form entities"| fmd
    ee -->|"unavailable entities"| uav
    ee -->|"config_service"| cfg

    main -->|"preload dialog + progress (via ProjectFlow)"| pload
    pflow -->|"preload_cached"| std
    pload -->|"estimate/should_confirm"| std

    fd -->|"xml_repo (IXmlRepository)"| xmlr
    fd -->|"cache (ICache)"| cache
    fd -->|"detail_panel (IDetailPanel)"| dp
    fd -->|"batch_panel (IBatchPanel)"| bp
    fd -->|"entertainment"| ent
    fd -->|"fun_presenter (FunPresenter)"| fp
    fd -->|"filter_menus (FilterMenu[])"| fm
    fd -->|"session (FileSession)"| fs
    fd -->|"TableController"| tc
    fd -->|"buttons via CommandRegistry"| creg
    ee -->|"undo/redo/add/delete/page dispatch"| creg

    fs -->|"state + ops (rows/undo/search/pagination/dirty)"| sc
    fs -->|"state + ops"| pag
    fs -->|"state + ops"| dirty
    fs -->|"state + ops"| undo
    fs -->|"SaveCommand / RandomizeCommand"| cmd
    fs -->|"xml_repo (IXmlRepository)"| xmlr
    fs -->|"cache (ICache)"| cache

    fp -->|"presentation + dialogs"| ent

    evd -->|"event_repo"| evr
    evd -->|"cache"| cache
    evd -->|"TableController"| tc
    evd -->|"UndoManager"| undo
    evd -->|"buttons via CommandRegistry"| creg

    std -->|"XmlSettingsRepository"| sxmlr
    std -->|"JsonSettingsRepository"| sjsonr
    std -->|"TableController"| tc
    std -->|"buttons via CommandRegistry"| creg
    std -->|"get_renderer/get_columns"| cent
    std -->|"get_renderer/get_columns"| exp
    fmd -->|"JsonSettingsRepository.load_doc/save_doc"| sjsonr
    fmd -->|"get_form_schema_for_path/build_auto_form_schema"| fschema
    fmd -->|"save button via CommandRegistry"| creg
    fmd -->|"schemas"| exp
    uav -->|"is_not_yet_available/get_mod_handler"| modh

    xmlr -->|"cache"| cache
    xmlr -->|"rows: RowData"| row
    evr -->|"cache"| cache
    evr -->|"rows: RowData"| row
    sxmlr -->|"RowData"| row
    sjsonr -->|"RowData"| row

    tc -->|"FieldDef/RowData"| models
    bp --> tc

    prj -->|"Project[]"| proj
    cfg -->|"ce: cfgeconomycore.xml"| xmlr
    econ -->|"types_dir/file list"| proj
    econ -->|"get_expansion_files"| exp
    prof -->|"scan_profiles(profiles_dir)"| proj
    ee -->|"profile_service (IProfileService)"| prof

    cm -->|"IRemoteConnection"| factory
    factory --> ssh
    factory --> ftp
    cm -->|"ConnectionConfig[]"| cr
    cm -->|"ConnectionConfig"| conncfg
    cr -->|"ConnectionConfig"| conncfg
    rss -->|"uses"| cm
    rss -->|"create()"| factory
```