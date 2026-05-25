# Querying

All query-building methods return a **new cloned entity** — the original is never mutated. Chains are composed by calling methods in sequence.

Call `.build()` to emit SQL and a tuple of parameters:

```python
>>> from norm import Table, Field, PrimaryKey, Unique, Index, field, db
>>> class User(Table):
...     id:    PrimaryKey[int] = field(default=db.serial())
...     name:  Field[str]
...     email: Unique[str]
...     bio:   Field[str | None]
...
>>> class Post(Table):
...     id:      PrimaryKey[int] = field(default=db.serial())
...     user_id: Field[int]
...     title:   Field[str]
...     body:    Field[str | None]
...
>>> class Product(Table):
...     id:       PrimaryKey[int] = field(default=db.serial())
...     price:    Field[float]
...     tax:      Field[float]
...     category: Field[str]
...
>>> class A(Table):
...     id: PrimaryKey[int] = field(default=db.serial())
...
>>> class B(Table):
...     id: PrimaryKey[int] = field(default=db.serial())
...
>>> User.select(User.id).build()
('SELECT "users"."id" FROM "public"."users"', ())

```

`build()` accepts an optional `dialect` argument (defaults to `PostgresDialect`).

---

## select / select_all

```python
>>> User.select(User.id, User.name).build()
('SELECT "users"."id","users"."name" FROM "public"."users"', ())

>>> User.select_all().build()
('SELECT "users"."id","users"."name","users"."email","users"."bio" FROM "public"."users"', ())

```

When no columns are selected, the SQL emits no column list (`SELECT FROM ...`), which is rarely useful — always call `select()` or `select_all()`.

---

## where (filters)

Multiple `.where()` calls are combined with AND:

```python
>>> q = User.select(User.id).where(User.email == "alice@example.com")
>>> q = q.where(User.id > 10)
>>> q.build()
('SELECT "users"."id" FROM "public"."users" WHERE "users"."email"=$1 AND "users"."id">$2', ('alice@example.com', 10))

```

Combine filters with `&` (AND) and `|` (OR):

```python
>>> f = (User.id > 10) & (User.email.ilike("%@example.com"))
>>> User.select(User.id).where(f).build()
('SELECT "users"."id" FROM "public"."users" WHERE "users"."id">$1 AND "users"."email" ILIKE $2', (10, '%@example.com'))

>>> f2 = (User.id == 1) | (User.id == 2)
>>> User.select(User.id).where(f2).build()
('SELECT "users"."id" FROM "public"."users" WHERE "users"."id"=$1 OR "users"."id"=$2', (1, 2))

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
('SELECT "users"."id" FROM "public"."users" WHERE "users"."email" IS NULL', ())

>>> User.select(User.id).where(User.id.between(10, 20)).build()
('SELECT "users"."id" FROM "public"."users" WHERE "users"."id" BETWEEN $1 AND $2', (10, 20))

>>> User.select(User.id).where(User.id.isin([1, 2, 3])).build()
('SELECT "users"."id" FROM "public"."users" WHERE "users"."id" IN ($1,$2,$3)', (1, 2, 3))

>>> User.select(User.id).where(User.name.like("Al%")).build()
('SELECT "users"."id" FROM "public"."users" WHERE "users"."name" LIKE $1', ('Al%',))

>>> User.select(User.id).where(User.name == User.email).build()
('SELECT "users"."id" FROM "public"."users" WHERE "users"."email"="users"."name"', ())

```

---

## order_by

```python
>>> User.select(User.id).order_by(User.name).build()
('SELECT "users"."id" FROM "public"."users" ORDER BY "users"."name" ASC', ())

>>> User.select(User.id).order_by(User.name, desc=True).build()
('SELECT "users"."id" FROM "public"."users" ORDER BY "users"."name" DESC', ())

>>> User.select(User.id).order_by(User.name.desc()).build()
('SELECT "users"."id" FROM "public"."users" ORDER BY "users"."name" DESC', ())

>>> User.select(User.id).order_by(User.name.asc(), User.id.desc()).build()
('SELECT "users"."id" FROM "public"."users" ORDER BY "users"."name" ASC,"users"."id" DESC', ())

```

---

## limit / offset

```python
>>> User.select(User.id).limit(10).build()
('SELECT "users"."id" FROM "public"."users" LIMIT 10', ())

>>> User.select(User.id).limit(10).offset(20).build()
('SELECT "users"."id" FROM "public"."users" LIMIT 10 OFFSET 20', ())

```

---

## distinct

```python
>>> User.select(User.email).distinct().build()
('SELECT DISTINCT "users"."email" FROM "public"."users"', ())

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
('SELECT "posts"."id","posts"."title","users"."name" FROM "public"."posts" JOIN "public"."users" ON "users"."id"="posts"."user_id"', ())

>>> Post.select(Post.id).left_join(User, on=Post.user_id == User.id).build()
('SELECT "posts"."id" FROM "public"."posts" LEFT JOIN "public"."users" ON "users"."id"="posts"."user_id"', ())

>>> Post.select(Post.id).right_join(User, on=Post.user_id == User.id).build()
('SELECT "posts"."id" FROM "public"."posts" RIGHT JOIN "public"."users" ON "users"."id"="posts"."user_id"', ())

>>> Post.select(Post.id).cross_join(User).build()
('SELECT "posts"."id" FROM "public"."posts" CROSS JOIN "public"."users"', ())

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
('SELECT "posts"."title","author"."name","editor"."name" FROM "public"."posts" JOIN "public"."users" "author" ON "author"."id"="posts"."user_id" JOIN "public"."users" "editor" ON "editor"."id"="posts"."user_id"', ())

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
('SELECT "users"."name","recent"."id" FROM "public"."users" JOIN (SELECT "posts"."id","posts"."user_id" FROM "public"."posts" WHERE "posts"."id">$1) "recent" ON "users"."id"="recent"."user_id"', (100,))

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
('SELECT "posts"."user_id",COUNT("posts"."id") "cnt" FROM "public"."posts" GROUP BY "posts"."user_id" HAVING COUNT("posts"."id")>$1', (5,))

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
('SELECT "posts"."user_id",COUNT("posts"."id") "total" FROM "public"."posts"', ())

```

---

## Set operations

### union

```python
>>> A.select(A.id).union(B.select(B.id)).build()
('(SELECT "as"."id" FROM "public"."as") UNION (SELECT "bs"."id" FROM "public"."bs")', ())

>>> A.select(A.id).union(B.select(B.id), all=True).build()
('(SELECT "as"."id" FROM "public"."as") UNION ALL (SELECT "bs"."id" FROM "public"."bs")', ())

```

### intersect

```python
>>> A.select(A.id).intersect(B.select(B.id)).build()
('(SELECT "as"."id" FROM "public"."as") INTERSECT (SELECT "bs"."id" FROM "public"."bs")', ())

```

### exclude (EXCEPT)

```python
>>> A.select(A.id).exclude(B.select(B.id)).build()
('(SELECT "as"."id" FROM "public"."as") EXCEPT (SELECT "bs"."id" FROM "public"."bs")', ())

```

Set operations support `.order_by()`, `.limit()`, and `.offset()` applied after the set op:

```python
>>> A.select(A.id).union(B.select(B.id)).order_by(A.id).limit(5).build()
('(SELECT "as"."id" FROM "public"."as") UNION (SELECT "bs"."id" FROM "public"."bs") ORDER BY "id" ASC LIMIT 5', ())

```

---

## Aliasing selected fields

`.aliased("name")` on a field changes its output column name:

```python
>>> User.select(User.email.aliased("contact")).build()
('SELECT "users"."email" "contact" FROM "public"."users"', ())

```

---

## cast

```python
>>> User.select(User.id.cast("TEXT").aliased("id_text")).build()
('SELECT CAST("users"."id" AS TEXT) "id_text" FROM "public"."users"', ())

```

---

## Arithmetic on fields

```python
>>> Product.select((Product.price + Product.tax).aliased("total")).build()
('SELECT "products"."price"+"products"."tax" "total" FROM "public"."products"', ())

>>> Product.select((Product.price * 2).aliased("doubled")).build()
('SELECT "products"."price"*$1 "doubled" FROM "public"."products"', (2,))

```

Supported operators: `+`, `-`, `*`, `/`. The right-hand side may be a literal or another `Field`.
