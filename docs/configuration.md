# Configuration

## pyproject.toml

Norm reads its configuration from the `[tool.norm]` table:

```toml
[tool.norm]
migrations_dir = "migrations"   # path to migration files directory
models = "myapp.models"         # dotted Python import path for Table/View definitions
```

Both keys are optional:

| Key | Default |
|-----|---------|
| `migrations_dir` | `./migrations` |
| `models` | `./models` or `./models.py` (whichever exists) |

---

## NormConfig

`NormConfig` is the dataclass that holds resolved configuration. Use it when calling migration internals programmatically:

```python
>>> from norm.migrations.config import NormConfig, load_config
>>> from pathlib import Path
>>> cfg = NormConfig(
...     migrations_dir=Path("migrations"),
...     models="myapp.models",
... )
>>> cfg.migrations_dir
PosixPath('migrations')
>>> cfg.models
'myapp.models'

```

```python
>>> cfg = load_config(Path("."))  # doctest: +SKIP
>>> cfg = load_config(  # doctest: +SKIP
...     Path("."),
...     migrations_dir_override="db/migrations",
...     models_override="myapp.db.models",
... )

```

`load_config` raises `FileNotFoundError` if no `pyproject.toml` is found and no overrides are given.

---

## Model discovery

Norm discovers `Table` and `View` subclasses through a global registry (`MODEL_REGISTRY`) populated by `NormMeta.__new__` at class-definition time.

```python
>>> from norm.migrations.registry import MODEL_REGISTRY
>>> from norm import Table, Field, PrimaryKey, field, db
>>> class Widget(Table):
...     id:   PrimaryKey[int] = field(default=db.serial())
...     name: Field[str]
...
>>> any("Widget" in key for key in MODEL_REGISTRY)
True

```

`models_for(cfg)` imports the configured models module (which triggers registration) and returns the registered types:

```python
>>> from norm.migrations.discovery import models_for  # doctest: +SKIP
>>> tables = models_for(cfg)  # doctest: +SKIP

```

### Layout conventions

Norm infers the Postgres schema from the module path when the word `models` appears in it:

```
myapp/
  auth/
    models.py   →  schema inferred as "auth"
  commerce/
    models.py   →  schema inferred as "commerce"
  models.py     →  no schema (public)
```

Override with `TableMeta(schema="...")` to disable inference.

---

## Dialect

The `Dialect` protocol controls how parameterised placeholders are rendered. The only implementation is `PostgresDialect`, which emits `$1`, `$2`, … (the asyncpg / libpq format):

```python
>>> from norm.dialect import PostgresDialect
>>> from norm import Table, Field, PrimaryKey, field, TableMeta, db
>>> class MyTable(Table):
...     __meta__ = TableMeta(schema="public")
...     id:   PrimaryKey[int] = field(default=db.serial())
...     name: Field[str]
...
>>> MyTable.select(MyTable.id).build(PostgresDialect())
('SELECT "my_tables"."id" FROM "public"."my_tables"', ())

```

Pass a `Dialect` instance to `build()` or to `AsyncConnection(raw, dialect=...)`.
