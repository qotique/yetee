# Types Editor

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

Editor for DayZ `cfgeconomycore.xml` type files. Built with Python and [Flet](https://flet.dev/).

---

# Редактор Types

Редактор файлов types для `cfgeconomycore.xml` в DayZ. Написан на Python с использованием [Flet](https://flet.dev/).

## Features

- **Open `cfgeconomycore.xml`** via native file picker
- **Edit type files** in a table UI with inline editing (nominal, lifetime, restock, min, quantmin, quantmax, cost, flags, category, usage, value)
- **Create new type files** — auto-registers in the CE block
- **Delete type files** — removes from config and disk
- **Batch update** — edit multiple types in one file at once
- **Pagination & search** for large type lists (supports `|` for OR queries, e.g. `AK101|AK74`)
- **Cross-platform** — native desktop builds for Windows and Linux

## Возможности

- **Открытие `cfgeconomycore.xml`** через нативный файловый диалог
- **Редактирование типов** в таблице с inline-редактированием (nominal, lifetime, restock, min, quantmin, quantmax, cost, flags, category, usage, value)
- **Создание новых файлов** — авторегистрация в CE блоке
- **Удаление файлов** — удаление из конфига и с диска
- **Пакетное обновление** — редактирование нескольких типов в одном файле сразу
- **Пагинация и поиск** по большим спискам типов (поддержка `|` для OR запросов, например `AK101|AK74`)
- **Кроссплатформенность** — нативные сборки для Windows и Linux

## Use Cases / Сценарии использования

### Vanilla `cfgeconomycore.xml` (без CE блока)

Ванильный `cfgeconomycore.xml` не содержит CE блока. Редактор создаст его автоматически.

1. Скачайте папку `mpmissions/<map_name>/` с сервера себе на компьютер
2. Откройте приложение
3. Выберите `mpmissions/<map_name>/cfgeconomycore.xml`
4. В выпадающем списке файлов напишите `types.xml` — он будет создан и подключён к CE блоку

Директория CE файлов — `mpmissions/<map_name>/db/`.

### Vanilla `cfgeconomycore.xml` (no CE block)

Vanilla `cfgeconomycore.xml` does not contain a CE block. The editor will create it automatically.

1. Download `mpmissions/<map_name>/` from your server
2. Open the app
3. Select `mpmissions/<map_name>/cfgeconomycore.xml`
4. Type `types.xml` in the file dropdown — it will be created and registered in the CE block

The CE files directory is `mpmissions/<map_name>/db/`.

### Custom type file (`mod_name.xml`)

You can create a new file with any name (e.g. `my_mod_types.xml`). If the file doesn't exist yet — it will be created with the standard XML template and automatically registered in the CE block. If the file already exists in the `db/` folder — it will be connected to the config.

Можно создать новый файл с любым именем (например, `my_mod_types.xml`). Если файла нет — он создастся с стандартным XML-шаблоном и автоматически пропишется в CE блок. Если файл уже существует в папке `db/` — он подключится в конфиг.

### Existing `types.xml` in `db/`

Point the editor to `cfgeconomycore.xml`. The editor reads the CE block, finds `types.xml` (or any other registered files), and loads them for editing.

Укажите путь к `cfgeconomycore.xml`. Редактор прочитает CE блок, найдёт `types.xml` (или другие зарегистрированные файлы) и загрузит их для редактирования.

## Installation

### From Releases (Recommended)

Download the latest binary for your OS from the [Releases](https://github.com/qotique/TypesEditor/releases) page:

- **Linux**: `types_editor_linux`
- **Windows**: `types_editor_windows.exe`

Make executable and run (Linux):

```bash
chmod +x types_editor_linux
./types_editor_linux
```

### From Source

```bash
pip install uv
uv sync --group dev
uv run flet run
```

## Установка

### Из релизов (Рекомендуется)

Скачайте готовый бинарник для вашей ОС со страницы [Releases](https://github.com/qotique/TypesEditor/releases):

- **Linux**: `types_editor_linux`
- **Windows**: `types_editor_windows.exe`

Сделайте исполняемым и запустите (Linux):

```bash
chmod +x types_editor_linux
./types_editor_linux
```

### Из исходников

```bash
pip install uv
uv sync --group dev
uv run flet run
```

## Usage / Использование

1. Launch the app (double-click binary or `uv run flet run`)
2. Click **"Select cfgeconomycore.xml"**
3. Pick your server's config file
4. Edit type files in the table — all changes are inline
5. Click **Save** to persist changes
6. Upload the modified files back to your server

---

1. Запустите приложение (двойной клик по бинарнику или `uv run flet run`)
2. Нажмите **"Select cfgeconomycore.xml"**
3. Выберите конфиг вашего сервера
4. Редактируйте типы в таблице — изменения применяются сразу
5. Нажмите **Save** для сохранения
6. Загрузите изменённые файлы обратно на сервер

## Testing / Тестирование

```bash
uv run pytest tests/ -v
```

## Project Structure / Структура проекта

```
types_editor/
├── src/
│   ├── main.py              # Flet GUI application
│   ├── file_display.py       # Type file table UI with inline editing
│   └── etree.py              # XML parsing utilities
├── tests/
│   └── test_main.py          # Tests
├── .github/workflows/
│   └── build.yml             # CI: test, build, release
├── pyproject.toml
└── README.md
```

## License / Лицензия

Licensed under the [MIT License](LICENSE).