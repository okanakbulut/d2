# 141 — Model snapshot + diff + codegen + CLI for tables

Status: needs-triage
Type: AFK

## Parent

[14 — Django-style Migration System](14-schema-metadata-and-ddl.md)

## What to build

The first end-to-end self-service flow: declare a `Table` model → run `make` → run `apply` → table exists. After this slice, a user can:

1. Declare a `class User(Table)` with typed `Field[T]` annotations
2. Add `[tool.norm] migrations_dir = "migrations"` to `pyproject.toml` (or rely on convention)
3. Run `python -m norm.migrations make` — generates `migrations/0001_initial.py` with `CreateTable` op + `reverse_operations = [DropTable(...)]`
4. Run `python -m norm.migrations apply` — table created, row in `norm_migrations`
5. Run `python -m norm.migrations check` — silent, exit 0

### Scope

- **Registry**: `NormMeta.__new__` populates `_MODEL_REGISTRY: dict[str, type]` (keyed by `module.qualname`) when `"__table__" not in namespace`. Both `Table` and `View` subclasses register; clones/aliases/set-ops never do. `norm/migrations/registry.py` exposes `collect_models()`.
- **Snapshot** (`snapshot.py`): `models_to_schema_state(models)` for `Table` subclasses only. Reads `cls.__table__`, `cls.__meta__.schema`, `cls.__fields__`. Nullability derived from `Field[X | None]` (extend `_parse_fields` for this). Python → SQL type mapping per the parent issue (`int` → `BIGINT`, `int + primary_key + db_default` → `BIGSERIAL`, etc.). No indexes/constraints/FKs/extensions in this slice.
- **Replay** (`replay.py`): `replay_migrations(paths)` reduces all migration files into a `SchemaState`. Sorts by filename.
- **Diff** (`draft.py`): `diff_states(current, target) -> tuple[list, list]` for table create/drop only. Returns `(forward, reverse)`.
- **Codegen** (`codegen.py`): writes `NNNN_<label>.py` with `operations` and `reverse_operations`. All fields passed by keyword (including defaults). Filename label derived from diff content when `--label` omitted (1 op → derive from op; otherwise `auto`). Identifier-length validation deferred to 143.
- **Config** (`config.py`): reads `[tool.norm]` from `pyproject.toml` (`migrations_dir`, `models`). Conventional fallback: `models.py` or `models/` in CWD. `--migrations-dir` / `--models` CLI overrides.
- **CLI** (`__main__.py`): `make`, `apply`, `check` subcommands. `make` exits 0 silently with "No changes detected." when diff is empty. `check` exits non-zero if diff is non-empty.

Out of scope: column modifications on existing tables (142), constraints/indexes (143), FKs (144), views (145), extensions/schemas (146), reverse_operations for non-trivial ops (147 covers full path), escape hatches (148).

## Acceptance criteria

- [ ] `_MODEL_REGISTRY` populated by `NormMeta.__new__` only when `__table__` not in namespace
- [ ] Both `Table` and `View` subclasses register; `clone()`, `aliased()`, `_make_set_op()` do NOT register
- [ ] `_parse_fields` extracts nullability from `Field[X | None]`
- [ ] `models_to_schema_state(models)` produces correct `SchemaState` for `Table` subclasses (columns only)
- [ ] Python → SQL type mapping covers: `int`, `str`, `float`, `bool`, `datetime`, `date`, `Decimal`, `uuid.UUID`, `dict`/`list`, `bytes`, and `X | None`
- [ ] `replay_migrations(paths)` reduces all files into a final `SchemaState`
- [ ] `diff_states(current, target)` detects new and dropped tables; returns `(forward, reverse)`
- [ ] `codegen.make_migration` writes a valid importable `.py` file with all fields passed by keyword
- [ ] Codegen derives filename label: 1 op → `create_<table>` / `drop_<table>`; otherwise `auto`
- [ ] `config.py` loads `[tool.norm]` from `pyproject.toml`; falls back to `models.py` / `models/` at CWD
- [ ] CLI `make` prints "No changes detected." and exits 0 when diff is empty
- [ ] CLI `apply` works against pending migrations produced by `make`
- [ ] CLI `check` exits 0 silently when in sync; non-zero with file + line on diff or import failure
- [ ] Integration test: declare a model, run `make` → file written, run `apply` → table exists, run `check` → silent
- [ ] Unit tests assert exact codegen output for a simple model

## Blocked by

- [140 — Tracer: hand-written CreateTable migration through `apply`](140-tracer-create-table-migration.md)
