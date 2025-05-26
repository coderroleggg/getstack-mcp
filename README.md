# GetStack Templates MCP Server

MCP сервер для управления шаблонами из репозитория [getstack-templates](https://github.com/coderroleggg/getstack-templates).

## Возможности

- Получение списка доступных шаблонов
- Использование (клонирование) шаблона в указанную папку

## Установка

### С использованием uv

```bash
uv venv
source .venv/bin/activate
uv pip install -e .
```

## Использование

### Доступные команды

#### 1. get_templates

Получает список всех доступных шаблонов из репозитория.

**Параметры:** нет

**Возвращает:**
- `success`: boolean - статус операции
- `templates`: array - список шаблонов с информацией:
  - `name`: имя шаблона (папки)
  - `path`: путь в репозитории
  - `url`: URL на GitHub
- `count`: количество шаблонов
- `error`: сообщение об ошибке (если есть)

#### 2. use_template

Клонирует выбранный шаблон в указанную папку проекта.

**Параметры:**
- `template_name`: string - имя шаблона для использования
- `current_folder`: string - абсолютный путь к папке проекта, куда скопировать шаблон

**Возвращает:**
- `success`: boolean - статус операции
- `template_name`: имя использованного шаблона
- `target_folder`: абсолютный путь к папке назначения
- `files_copied`: количество скопированных файлов
- `files`: список скопированных файлов
- `error`: сообщение об ошибке (если есть)

## Пример использования с Claude Desktop

1. Добавьте сервер в конфигурацию Claude Desktop:

```json
{
  "mcpServers": {
    "getstack": {
      "command": "uv",
      "args": [
        "run",
        "--directory",
        "/Users/olegstefanov/Base/Prog/get-stack/mcp", // путь до папки с MCP
        "server"
      ],
      "description": "MCP server for getting templates"
    }
  }
}
```

2. Используйте команды в Claude:
   - "Покажи список доступных шаблонов"
   - "Используй шаблон nextjs-app в папке ~/my-project"

## Требования

- Python 3.10+
- Доступ к интернету для работы с GitHub API
- Git для клонирования репозитория

## Лицензия

MIT
