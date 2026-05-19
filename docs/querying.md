# Querying

All query-building methods return a **new cloned entity** — the original is never mutated. Chains are composed by calling methods in sequence.

Call `.build()` to emit SQL and a tuple of parameters:

```python
>>> from norm import Table, Field, PrimaryKey, Unique, Index, field
>>> class User(Table):
...     id:    PrimaryKey[int] = field(db_default=True)
...     name:  Field[str]
...     email: Unique[str]
...     bio:   Field[str | None]
...
>>> class Post(Table):
...     id:      PrimaryKey[int] = field(db_default=True)
...     user_id: Field[int]
...     title:   Field[str]
...     body:    Field[str | None]
...
>>> class Product(Table):
...     id:       PrimaryKey[int] = field(db_default=True)
...     price:    Field[float]
...     tax:      Field[float]
...     category: Field[str]
...
>>> class A(Table):
...     id: PrimaryKey[int] = field(db_default=True)
...
>>> class B(Table):
...     id: PrimaryKey[int] = field(db_default=True)
...
>>> User.select(User.id).build()
('SELECT "user"."id" FROM "public"."user"', ())

```

`build()` accepts an optional `dialect` argument (defaults to `PostgresDialect`).

---

## select / select_all

```python
>>> User.select(User.id, User.name).build()
('SELECT "user"."id","user"."name" FROM "public"."user"', ())

>>> User.select_all().build()
('SELECT "user"."id","user"."name","user"."email","user"."bio" FROM "public"."user"', ())

```

When no columns are selected, the SQL emits no column list (`SELECT FROM ...`), which is rarely useful — always call `select()` or `select_all()`.

---

## where (filters)

Multiple `.where()` calls are combined with AND:

```python
>>> q = User.select(User.id).where(User.email == "alice@example.com")
>>> q = q.where(User.id > 10)
>>> q.build()
('SELECT "user"."id" FROM "public"."user" WHERE "user"."email"=$1 AND "user"."id">$2', ('alice@example.com', 10))

```

Combine filters with `&` (AND) and `|` (OR):

```python
>>> f = (User.id > 10) & (User.email.ilike("%@example.com"))
>>> User.select(User.id).where(f).build()
('SELECT "user"."id" FROM "public"."user" WHERE "user"."id">$1 AND "user"."email" ILIKE $2', (10, '%@example.com'))

>>> f2 = (User.id == 1) | (User.id == 2)
>>> User.select(User.id).where(f2).build()
('SELECT "user"."id" FROM "public"."user" WHERE "user"."id"=$1 OR "user"."id"=$2', (1, 2))

```

### Available filter operations

| Method / operator | SQL |
|-------------------|-----|
| `field == value` | `field = $n` |
| `field != value` | `field <> $n` |
| `field < value` | `field < $n` |
| `field <= value` | `field <= $n` |
| `field > value` | `field > $n` |
| `field >= value` | `field >= $n` |
| `field == other_field` | `field = other_field` (column-to-column) |
| `field.like(pat)` | `field LIKE $n` |
| `field.ilike(pat)` | `field ILIKE $n` |
| `field.isnull()` | `field IS NULL` |
| `field.isnotnull()` | `field IS NOT NULL` |
| `field.between(lo, hi)` | `field BETWEEN $n AND $m` |
| `field.isin([...])` | `field IN ($1, $2, ...)` |
| `field.notin([...])` | `field NOT IN ($1, $2, ...)` |

```python
>>> User.select(User.id).where(User.email.isnull()).build()
('SELECT "user"."id" FROM "public"."user" WHERE "user"."email" IS NULL', ())

>>> User.select(User.id).where(User.id.between(10, 20)).build()
('SELECT "user"."id" FROM "public"."user" WHERE "user"."id" BETWEEN $1 AND $2', (10, 20))

>>> User.select(User.id).where(User.id.isin([1, 2, 3])).build()
('SELECT "user"."id" FROM "public"."user" WHERE "user"."id" IN ($1,$2,$3)', (1, 2, 3))

>>> User.select(User.id).where(User.name.like("Al%")).build()
('SELECT "user"."id" FROM "public"."user" WHERE "user"."name" LIKE $1', ('Al%',))

>>> User.select(User.id).where(User.name == User.email).build()
('SELECT "user"."id" FROM "public"."user" WHERE "user"."email"="user"."name"', ())

```

---

## order_by

```python
>>> User.select(User.id).order_by(User.name).build()
('SELECT "user"."id" FROM "public"."user" ORDER BY "user"."name" ASC', ())

>>> User.select(User.id).order_by(User.name, desc=True).build()
('SELECT "user"."id" FROM "public"."user" ORDER BY "user"."name" DESC', ())

>>> User.select(User.id).order_by(User.name.desc()).build()
('SELECT "user"."id" FROM "public"."user" ORDER BY "user"."name" DESC', ())

>>> User.select(User.id).order_by(User.name.asc(), User.id.desc()).build()
('SELECT "user"."id" FROM "public"."user" ORDER BY "user"."name" ASC,"user"."id" DESC', ())

```

---

## limit / offset

```python
>>> User.select(User.id).limit(10).build()
('SELECT "user"."id" FROM "public"."user" LIMIT 10', ())

>>> User.select(User.id).limit(10).offset(20).build()
('SELECT "user"."id" FROM "public"."user" LIMIT 10 OFFSET 20', ())

```

---

## distinct

```python
>>> User.select(User.email).distinct().build()
('SELECT DISTINCT "user"."email" FROM "public"."user"', ())

```

---

## Joins

All join methods accept `on=` as a filter (or compound filter):

```python
>>> q = (
...     Post
...     .select(Post.id, Post.title, User.name)
...     .join(User, on=Post.user_id == User.id)
... )
>>> q.build()
('SELECT "post"."id","post"."title","user"."name" FROM "public"."post" JOIN "public"."user" ON "user"."id"="post"."user_id"', ())

>>> Post.select(Post.id).left_join(User, on=Post.user_id == User.id).build()
('SELECT "post"."id" FROM "public"."post" LEFT JOIN "public"."user" ON "user"."id"="post"."user_id"', ())

>>> Post.select(Post.id).right_join(User, on=Post.user_id == User.id).build()
('SELECT "post"."id" FROM "public"."post" RIGHT JOIN "public"."user" ON "user"."id"="post"."user_id"', ())

>>> Post.select(Post.id).cross_join(User).build()
('SELECT "post"."id" FROM "public"."post" CROSS JOIN "public"."user"', ())

```

### Self-join with alias

Use `.aliased()` on a plain entity to create a real table alias:

```python
>>> Author = User.aliased("author")
>>> Editor = User.aliased("editor")
>>> q = (
...     Post
...     .select(Post.title, Author.name, Editor.name)
...     .join(Author, on=Post.user_id == Author.id)
...     .join(Editor, on=Post.user_id == Editor.id)
... )
>>> q.build()
('SELECT "post"."title","author"."name","editor"."name" FROM "public"."post" JOIN "public"."user" "author" ON "author"."id"="post"."user_id" JOIN "public"."user" "editor" ON "editor"."id"="post"."user_id"', ())

```

### Join on a subquery

Build the subquery, call `.aliased()` to wrap it as a named subquery, then join:

```python
>>> recent = (
...     Post
...     .select(Post.id, Post.user_id)
...     .where(Post.id > 100)
...     .aliased("recent")
... )
>>> q = User.select(User.name, recent.id).join(recent, on=User.id == recent.user_id)
>>> q.build()
('SELECT "user"."name","recent"."id" FROM "public"."user" JOIN (SELECT "post"."id","post"."user_id" FROM "public"."post" WHERE "post"."id">$1) "recent" ON "user"."id"="recent"."user_id"', (100,))

```

---

## group_by / having

```python
>>> q = (
...     Post
...     .select(Post.user_id, Post.id.count().aliased("cnt"))
...     .group_by(Post.user_id)
...     .having(Post.id.count() > 5)
... )
>>> q.build()
('SELECT "post"."user_id",COUNT("post"."id") "cnt" FROM "public"."post" GROUP BY "post"."user_id" HAVING COUNT("post"."id")>$1', (5,))

```

---

## Aggregation

Field aggregation methods return a new `Field` that can be selected or used in `having`:

| Method | SQL |
|--------|-----|
| `field.count()` | `COUNT(field)` |
| `field.count(distinct=True)` | `COUNT(DISTINCT field)` |
| `field.sum()` | `SUM(field)` |
| `field.min()` | `MIN(field)` |
| `field.max()` | `MAX(field)` |
| `field.avg()` | `AVG(field)` |
| `field.coalesce(default)` | `COALESCE(field, $n)` |

Always `.aliased("name")` an aggregate so the result has a predictable column name:

```python
>>> Post.select(Post.user_id, Post.id.count().aliased("total")).build()
('SELECT "post"."user_id",COUNT("post"."id") "total" FROM "public"."post"', ())

```

---

## Set operations

### union

```python
>>> A.select(A.id).union(B.select(B.id)).build()
('(SELECT "a"."id" FROM "public"."a") UNION (SELECT "b"."id" FROM "public"."b")', ())

>>> A.select(A.id).union(B.select(B.id), all=True).build()
('(SELECT "a"."id" FROM "public"."a") UNION ALL (SELECT "b"."id" FROM "public"."b")', ())

```

### intersect

```python
>>> A.select(A.id).intersect(B.select(B.id)).build()
('(SELECT "a"."id" FROM "public"."a") INTERSECT (SELECT "b"."id" FROM "public"."b")', ())

```

### exclude (EXCEPT)

```python
>>> A.select(A.id).exclude(B.select(B.id)).build()
('(SELECT "a"."id" FROM "public"."a") EXCEPT (SELECT "b"."id" FROM "public"."b")', ())

```

Set operations support `.order_by()`, `.limit()`, and `.offset()` applied after the set op:

```python
>>> A.select(A.id).union(B.select(B.id)).order_by(A.id).limit(5).build()
('(SELECT "a"."id" FROM "public"."a") UNION (SELECT "b"."id" FROM "public"."b") ORDER BY "id" ASC LIMIT 5', ())

```

---

## Aliasing selected fields

`.aliased("name")` on a field changes its output column name:

```python
>>> User.select(User.email.aliased("contact")).build()
('SELECT "user"."email" "contact" FROM "public"."user"', ())

```

---

## cast

```python
>>> User.select(User.id.cast("TEXT").aliased("id_text")).build()
('SELECT CAST("user"."id" AS TEXT) "id_text" FROM "public"."user"', ())

```

---

## Arithmetic on fields

```python
>>> Product.select((Product.price + Product.tax).aliased("total")).build()
('SELECT "product"."price"+"product"."tax" "total" FROM "public"."product"', ())

>>> Product.select((Product.price * 2).aliased("doubled")).build()
('SELECT "product"."price"*$1 "doubled" FROM "public"."product"', (2,))

```

Supported operators: `+`, `-`, `*`, `/`. The right-hand side may be a literal or another `Field`.
