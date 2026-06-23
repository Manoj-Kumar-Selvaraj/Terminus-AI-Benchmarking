# Task Subtypes

Subtypes, also called subcategories, are a second classification axis in `task.toml`.

A task can align with multiple subcategories. If none apply, leave the field empty:

```toml
subcategories = []
```

Supported values:

- `long_context`
- `tool_specific`
- `api_integration`
- `db_interaction`
- `ui_building`

## Long Context

Tasks that require models to use large context windows by reading large documents.

Threshold:

- File must be at least 50k tokens.
- The task cannot be solvable through simple programmatic parsing or keyword search.
- The task must rely on semantic understanding.

Formats include PDF, DOCX, Markdown, TXT, HTML, JSON, YAML, CSV, chat logs, and email threads.

## Tool Specific

Tasks targeting specialized tools, SDKs, or APIs where models tend to underperform.

Examples:

- Blender
- FFmpeg
- ImageMagick
- Graphviz
- MLflow
- WandB
- Prefect
- Superset
- GIMP
- QGIS

Use tags to name the specific tool.

## API Integration

Tasks that involve building, interacting with, or debugging APIs.

Requirements:

- API source code is included in the environment.
- APIs are mocked or run inside Docker.
- No external API dependencies.
- Agent interacts through the terminal only.

Examples: Flask, Ruby on Rails, Spring Boot, Django, Express.js, Fastify, Play Framework, Gin, Rust API frameworks.

Avoid overusing FastAPI because it is already common in other datasets.

## DB Interaction

Tasks that require gathering context or solving problems through a real database.

Database types include SQL, NoSQL, vector databases, and in-memory databases.

Avoid making DB tasks mostly flat-file CSV tasks. The agent should need to interact with the database engine.

## UI Building

Tasks that create, edit, or update a user interface.

UI tasks should use the UI skeleton and are verified with Playwright rather than the usual pytest validators.
