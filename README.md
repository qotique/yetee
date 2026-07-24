# Types Editor

Editor for DayZ `cfgeconomycore.xml` type files. Built with Python and [Flet](https://flet.dev/).

---

# Редактор Types

Редактор файлов types для `cfgeconomycore.xml` в DayZ. Написан на Python с использованием [Flet](https://flet.dev/).

## Features

- **Open `cfgeconomycore.xml`** via native file picker
- **Edit type files** in a table UI with inline editing (nominal, lifetime, restock, min, quantmin, quantmax, cost, flags, category, usage, value)
- **Create new type files** — auto-registers in the CE block
- **Delete type files** — removes from config and disk
- **Pagination & search** for large type lists
- **Cross-platform** — native desktop builds for Windows and Linux

## Возможности

- **Открытие `cfgeconomycore.xml`** через нативный файловый диалог
- **Редактирование типов** в таблице с inline-редактированием (nominal, lifetime, restock, min, quantmin, quantmax, cost, flags, category, usage, value)
- **Создание новых файлов** — авторегистрация в CE блоке
- **Удаление файлов** — удаление из конфига и с диска
- **Пагинация и поиск** по большим спискам типов
- **Кроссплатформенность** — нативные сборки для Windows и Linux

## Use Cases / Сценарии использования

### Vanilla `types.xml`

If your server only has a single `types.xml` in the `db/` folder — just select `cfgeconomycore.xml`. The editor will find the CE block and load its type files.

Если у вас стандартный `types.xml` в папке `db/` — просто выберите `cfgeconomycore.xml`. Редактор найдёт CE блок и загрузит типовые файлы.

### `cfgeconomycore.xml` without CE block

If the CE block is missing, the editor will create it automatically with `folder="db"`.

Если CE блок отсутствует, редактор создаст его автоматически с `folder="db"`.

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

MIT