# Schema

## Table and View

```python
>>> from norm import Table, View, Field, PrimaryKey, ForeignKey, Unique, Index, field, TableMeta, db
>>> from norm.model import IndexDef
>>> class MyTable(Table):
...     id: PrimaryKey[int]
...
>>> class MyView(View):
...     id: Field[int]
...

```

`Table` supports SELECT, INSERT, UPDATE, and DELETE.  
`View` is read-only (SELECT only).

Both use `NormMeta` as their metaclass, which on class creation:
1. Parses type annotations to build `Field` proxies
2. Infers the table name from the class name (CamelCase → snake_case, strips trailing `Model`)
3. Registers the class in the global model registry used by migrations

## Field types

| Annotation | SQL meaning |
|------------|-------------|
| `Field[T]` | Plain column |
| `Column[T]` | Alias for `Field[T]` |
| `PrimaryKey[T]` | Column with `PRIMARY KEY` |
| `Unique[T]` | Column with `UNIQUE` constraint |
| `Index[T]` | Column with an index (no unique constraint) |

`Field[T | None]` (or `Field[Optional[T]]`) marks the column as nullable.

Enum classes work as column types: str-based enums (`StrEnum`, `class X(str, Enum)`) are stored as `TEXT`, int-based enums (`IntEnum`) as `INTEGER`. Values travel on the wire as their base str/int value.

```python
>>> class Article(Table):
...     id:         PrimaryKey[int]          # primary key
...     slug:       Unique[str]              # unique column
...     views:      Index[int]               # indexed column
...     title:      Field[str]               # plain column
...     summary:    Field[str | None]        # nullable column
...

```

## field() helper

Use `field()` as the class-level default to attach metadata that annotations alone cannot express:

```python
>>> class Post(Table):
...     id:    PrimaryKey[int] = field(default=db.serial())
...     title: Field[str]
...
>>> class Comment(Table):
...     id:      PrimaryKey[int] = field(default=db.serial())
...     post_id: ForeignKey[Post] = field(on_delete=db.CASCADE)
...     body:    Field[str]
...     slug:    Field[str]      = field(name="url_slug")
...     flagged: Unique[str]     = field(unique=True)
...

```

`field()` parameters:

| Parameter | Type | Description |
|-----------|------|-------------|
| `default` | `DbExpr \| None` | DB-level default (e.g. `db.serial()`, `db.now()`) |
| `on_delete` | `ReferentialAction \| None` | FK delete action (`db.CASCADE`, `db.SET_NULL`, etc.) |
| `on_update` | `ReferentialAction \| None` | FK update action |
| `name` | `str \| None` | Override the column name in the database |
| `unique` | `bool` | Add a UNIQUE constraint |
| `index` | `bool` | Create an index on this column |

## TableMeta

`TableMeta` is set as `__meta__` on the class and controls table-level options:

```python
>>> class Order(Table):
...     __meta__ = TableMeta(
...         table="orders",
...         schema="commerce",
...         indexes=(
...             IndexDef(
...                 columns=("user_id", "created_at"),
...                 name="idx_orders_user_date",
...                 unique=False,
...                 method="BTREE",
...             ),
...         ),
...         extensions=("uuid-ossp",),
...     )
...     id:         PrimaryKey[int] = field(default=db.serial())
...     user_id:    Field[int]
...     created_at: Field[str]
...

```

`TableMeta` fields:

| Field | Type | Description |
|-------|------|-------------|
| `table` | `str \| None` | Override table name (default: snake_case of class name) |
| `schema` | `str \| None` | Postgres schema |
| `indexes` | `tuple[IndexDef, ...]` | Composite or method-specific indexes |
| `foreign_keys` | `tuple[ForeignKey, ...]` | Table-level FKs (rarely needed; prefer `ForeignKey[T]` annotation) |
| `extensions` | `tuple[str, ...]` | Extensions to ensure exist |

## ForeignKey

Declare foreign keys using the `ForeignKey[T]` type annotation, where `T` is the referenced `Table` class. Use `field(on_delete=...)` to set the referential action.

```python
>>> class User(Table):
...     id: PrimaryKey[int] = field(default=db.serial())
...
>>> class Profile(Table):
...     id:      PrimaryKey[int]  = field(default=db.serial())
...     user_id: ForeignKey[User] = field(on_delete=db.CASCADE)
...
>>> class Audit(Table):
...     id:      PrimaryKey[int]  = field(default=db.serial())
...     user_id: ForeignKey[User] = field(on_delete=db.SET_NULL)
...

```

Referential actions are constants on the `db` module: `db.CASCADE`, `db.SET_NULL`, `db.RESTRICT`, `db.NO_ACTION`, `db.SET_DEFAULT`.

## IndexDef

```python
>>> IndexDef(
...     columns=("col_a", "col_b"),
...     name="idx_my_table_ab",
...     unique=False,
...     method="GIN",
... )
IndexDef(columns=('col_a', 'col_b'), name='idx_my_table_ab', unique=False, method='GIN')

```

## Table name inference

Norm derives the table name from the class name automatically:

| Class name | Inferred table name |
|------------|---------------------|
| `User` | `user` |
| `BlogPost` | `blog_post` |
| `UserModel` | `user` (strips `Model` suffix) |

Override with `TableMeta(table="my_name")`.

## Schema inference from module path

If your models live in a package that contains `models` in the path, norm infers the schema from the parent package:

```
myapp/
  commerce/
    models.py   →  schema="commerce"
  auth/
    models.py   →  schema="auth"
```

Override with `TableMeta(schema="...")`.

## View with a query

Views can be backed by a norm query using the `query=` class keyword:

```python
>>> class ActiveUser(View, query=(
...     User
...     .select(User.id.aliased("id"))
...     .where(User.id.isnotnull())
... )):
...     id: Field[int]
...

```

Norm validates at class-creation time that the view's declared columns match the query's projected columns (name and type). This raises `TypeError` immediately if they diverge.
