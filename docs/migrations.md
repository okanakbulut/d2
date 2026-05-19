# Migrations

Norm's migration system compares your Table definitions against the history of applied migrations to produce a diff, then generates versioned Python files you can review, commit, and apply.

## Workflow

```
1. Edit Table / View definitions in Python
2. python -m norm.migrations make   →  generates migrations/NNNN_<label>.py
3. Review the generated file
4. python -m norm.migrations apply  →  runs pending files against the DB
5. python -m norm.migrations rollback <name>  →  reverses one migration
```

---

## CLI reference

All commands read `[tool.norm]` from `pyproject.toml` by default. Flags override the config.

### make

Diff the current schema against applied migrations and write a new migration file.

```bash
python -m norm.migrations make \
  [--migrations-dir ./migrations] \
  [--models myapp.models] \
  [--label my_description]
```

If there are no schema changes, the command exits without writing a file.

### check

Validate existing migration files (lint checks) and report schema drift without writing anything.

```bash
python -m norm.migrations check \
  [--migrations-dir ./migrations] \
  [--models myapp.models]
```

Checks performed:
- `atomic=True` migrations that contain `CREATE/DROP INDEX CONCURRENTLY` (which cannot run inside a transaction)
- `RunSQL` operations that contain DDL keywords (suggest using a DDL operation instead)

### apply

Apply all pending migrations to the database in name-sorted order.

```bash
python -m norm.migrations apply \
  --dsn postgresql://user:pass@host/dbname \
  [--migrations-dir ./migrations] \
  [--models myapp.models]
```

### rollback

Reverse the most recently applied migration. The migration must have `reverse_operations` defined.

```bash
python -m norm.migrations rollback <migration-name> \
  --dsn postgresql://user:pass@host/dbname \
  [--force]   # skip the "must be most recent" guard
```

---

## Migration files

A generated migration file looks like this:

```python
>>> from norm.migrations import Migration
>>> from norm.migrations.operations import (
...     CreateTable, DropTable, AddConstraint, ColumnDef,
... )
>>> class Migration0001(Migration):
...     name = "0001_create_user"
...     atomic = True
...     dependencies = []
...     operations = [
...         CreateTable(
...             table="user",
...             schema="public",
...             columns={
...                 "id":    ColumnDef(type="SERIAL", nullable=False, default=None, primary_key=True, has_sequence_default=True),
...                 "email": ColumnDef(type="TEXT",   nullable=False, default=None, primary_key=False),
...             },
...         ),
...         AddConstraint(
...             table="user",
...             schema="public",
...             constraint={"type": "unique", "name": "uq_user_email", "columns": ("email",)},
...         ),
...     ]
...     reverse_operations = [
...         DropTable(table="user", schema="public"),
...     ]
...
>>> Migration0001.name
'0001_create_user'
>>> Migration0001.atomic
True
>>> len(Migration0001.operations)
2

```

### Migration class attributes

| Attribute | Type | Description |
|-----------|------|-------------|
| `name` | `str` | Unique identifier (usually matches the filename stem) |
| `operations` | `list[Operation]` | Forward operations, applied in order |
| `reverse_operations` | `list[Operation] \| None` | Reverse operations; `None` means rollback is blocked |
| `dependencies` | `list[str]` | Names of migrations that must be applied first |
| `atomic` | `bool` | Wrap in a transaction (default `True`) |

Set `atomic = False` when operations cannot run inside a transaction — for example `CREATE INDEX CONCURRENTLY`.

---

## Operations reference

### Table operations

```python
>>> from norm.migrations.operations import (
...     CreateTable, DropTable, AddColumn, DropColumn, RenameColumn,
...     AlterColumnType, SetColumnNotNull, DropColumnNotNull,
...     SetColumnDefault, DropColumnDefault, AddConstraint, DropConstraint,
...     CreateIndex, DropIndex, CreateSchema, DropSchema,
...     CreateExtension, DropExtension, CreateView, DropView,
...     RunSQL, RunPython, ColumnDef,
... )
>>> CreateTable(table="users", schema="public", columns={
...     "id":   ColumnDef(type="SERIAL", nullable=False, default=None, primary_key=True, has_sequence_default=True),
...     "name": ColumnDef(type="TEXT",   nullable=False, default=None, primary_key=False),
... }).to_ddl()
'CREATE TABLE IF NOT EXISTS "public"."users" ("id" SERIAL NOT NULL PRIMARY KEY, "name" TEXT NOT NULL)'

>>> DropTable(table="users", schema="public").to_ddl()
'DROP TABLE IF EXISTS "public"."users"'

```

### Column operations

```python
>>> AddColumn(table="users", column="bio", type="TEXT", nullable=True, default=None, schema="public").to_ddl()
'ALTER TABLE "public"."users" ADD COLUMN "bio" TEXT'

>>> DropColumn(table="users", column="bio", schema="public").to_ddl()
'ALTER TABLE "public"."users" DROP COLUMN "bio"'

>>> RenameColumn(table="users", old_name="bio", new_name="about", schema="public").to_ddl()
'ALTER TABLE "public"."users" RENAME COLUMN "bio" TO "about"'

>>> AlterColumnType(table="users", column="score", type="BIGINT", schema="public").to_ddl()
'ALTER TABLE "public"."users" ALTER COLUMN "score" TYPE BIGINT'

>>> SetColumnNotNull(table="users", column="email", schema="public").to_ddl()
'ALTER TABLE "public"."users" ALTER COLUMN "email" SET NOT NULL'

>>> DropColumnNotNull(table="users", column="email", schema="public").to_ddl()
'ALTER TABLE "public"."users" ALTER COLUMN "email" DROP NOT NULL'

>>> SetColumnDefault(table="users", column="score", default="0", schema="public").to_ddl()
'ALTER TABLE "public"."users" ALTER COLUMN "score" SET DEFAULT 0'

>>> DropColumnDefault(table="users", column="score", schema="public").to_ddl()
'ALTER TABLE "public"."users" ALTER COLUMN "score" DROP DEFAULT'

```

### Constraint operations

```python
>>> AddConstraint(
...     table="users", schema="public",
...     constraint={"type": "unique", "name": "uq_users_email", "columns": ("email",)},
... ).to_ddl()
'DO $$ BEGIN ALTER TABLE "public"."users" ADD CONSTRAINT "uq_users_email" UNIQUE ("email"); EXCEPTION WHEN duplicate_object THEN NULL; END $$'

>>> AddConstraint(
...     table="posts", schema="public",
...     constraint={
...         "type": "foreign_key",
...         "name": "fk_posts_user_id",
...         "columns": ("user_id",),
...         "references_schema": "public",
...         "references_table": "users",
...         "references_column": "id",
...         "on_delete": "CASCADE",
...         "on_update": None,
...     },
... ).to_ddl()
'DO $$ BEGIN ALTER TABLE "public"."posts" ADD CONSTRAINT "fk_posts_user_id" FOREIGN KEY ("user_id") REFERENCES "public"."users" ("id") ON DELETE CASCADE; EXCEPTION WHEN duplicate_object THEN NULL; END $$'

>>> DropConstraint(table="users", name="uq_users_email", schema="public").to_ddl()
'ALTER TABLE "public"."users" DROP CONSTRAINT IF EXISTS "uq_users_email"'

```

### Index operations

```python
>>> CreateIndex(
...     table="posts",
...     columns=("user_id", "created_at"),
...     name="idx_posts_user_date",
...     method="BTREE",
...     unique=False,
...     concurrent=True,
...     schema="public",
... ).to_ddl()
'CREATE INDEX CONCURRENTLY IF NOT EXISTS "idx_posts_user_date" ON "public"."posts" USING BTREE ("user_id", "created_at")'

>>> DropIndex(name="idx_posts_user_date", concurrent=True, schema="public").to_ddl()
'DROP INDEX CONCURRENTLY IF EXISTS "public"."idx_posts_user_date"'

```

When `concurrent=True`, the migration **must** set `atomic = False`.

### Schema and extension operations

```python
>>> CreateSchema(name="analytics").to_ddl()
'CREATE SCHEMA IF NOT EXISTS "analytics"'

>>> DropSchema(name="analytics", cascade=False).to_ddl()
'DROP SCHEMA IF EXISTS "analytics"'

>>> CreateExtension(name="uuid-ossp").to_ddl()
'CREATE EXTENSION IF NOT EXISTS "uuid-ossp"'

>>> DropExtension(name="uuid-ossp").to_ddl()
'DROP EXTENSION IF EXISTS "uuid-ossp"'

```

### View operations

```python
>>> CreateView(
...     name="active_users",
...     definition="SELECT id, email FROM users WHERE email IS NOT NULL",
...     schema="public",
...     replace=True,
... ).to_ddl()
'CREATE OR REPLACE VIEW "public"."active_users" AS SELECT id, email FROM users WHERE email IS NOT NULL'

>>> DropView(name="active_users", schema="public", cascade=False).to_ddl()
'DROP VIEW IF EXISTS "public"."active_users"'

```

### Escape hatches

Use these only for data migrations or operations that norm's DDL system cannot express.

```python
>>> RunSQL(
...     sql="UPDATE users SET score = 0 WHERE score IS NULL",
...     reverse_sql="UPDATE users SET score = NULL WHERE score = 0",
... )
RunSQL(sql='UPDATE users SET score = 0 WHERE score IS NULL', reverse_sql='UPDATE users SET score = NULL WHERE score = 0')

```

`RunSQL.sql` is split on `;` — multiple statements are executed in sequence.

```python
>>> async def backfill(conn):  # doctest: +SKIP
...     rows = await conn.raw_fetch("SELECT id FROM users WHERE slug IS NULL")
...     for row in rows:
...         await conn.raw_execute(
...             "UPDATE users SET slug = $1 WHERE id = $2",
...             f"user-{row['id']}", row["id"],
...         )
...
>>> async def reverse_backfill(conn):  # doctest: +SKIP
...     await conn.raw_execute("UPDATE users SET slug = NULL")
...
>>> RunPython(fn=backfill, reverse_fn=reverse_backfill)  # doctest: +SKIP

```

`RunPython.fn` receives the `AsyncConnection` wrapper. It is awaited by the runner.

`RunSQL` and `RunPython` cannot be serialised to source — do not use `make` to generate them; write them by hand in the migration file.

---

## Tracking table

Norm records applied migrations in `norm_migrations` (created automatically):

```sql
CREATE TABLE IF NOT EXISTS norm_migrations (
    id         SERIAL PRIMARY KEY,
    name       TEXT NOT NULL UNIQUE,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
)
```

---

## CONCURRENTLY index safety

`CREATE INDEX CONCURRENTLY` and `DROP INDEX CONCURRENTLY` cannot run inside a transaction. For any migration that includes these:

1. Set `atomic = False` on the migration class.
2. Run `check` — it will warn if you forget.

If a concurrent index creation fails, Postgres may leave behind an `INVALID` index. The runner prints the recovery command automatically:

```
DROP INDEX CONCURRENTLY IF EXISTS "idx_name";
```
