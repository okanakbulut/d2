---
title: Advanced Queries
description: "CTEs, JSON output, prefetch, window functions, and scalar subqueries."
---

```python
>>> from norm import Table, Field, PrimaryKey, Unique, field, TableMeta, With, db
>>> class User(Table):
...     id:    PrimaryKey[int] = field(default=db.serial())
...     name:  Field[str]
...     email: Unique[str]
...
>>> class Post(Table):
...     id:      PrimaryKey[int] = field(default=db.serial())
...     user_id: Field[int]
...     title:   Field[str]
...
>>> class Comment(Table):
...     id:      PrimaryKey[int] = field(default=db.serial())
...     post_id: Field[int]
...     body:    Field[str]
...
>>> class EmpSalary(Table):
...     __meta__ = TableMeta(table="empsalary")
...     depname: Field[str]
...     empno:   Field[int]
...     salary:  Field[int]
...

```

## CTEs (Common Table Expressions)

Use `With()` to attach named CTEs to a query. Each CTE is a query aliased to a name, and the final query references them like tables.

```python
>>> active = (
...     User
...     .select(User.id, User.email)
...     .where(User.email.isnotnull())
...     .aliased("active_users")
... )
>>> q = With(
...     active,
...     query=Post.select(Post.id, active.email).join(active, on=Post.user_id == active.id),
... )
>>> q.build()
('WITH "active_users" AS (SELECT "users"."id","users"."email" FROM "public"."users" WHERE "users"."email" IS NOT NULL) SELECT "posts"."id","active_users"."email" FROM "public"."posts" JOIN "active_users" ON "posts"."user_id"="active_users"."id"', ())

```

### Multiple CTEs

Pass all CTE aliases before `query=`:

```python
>>> cte_a = (
...     User
...     .select(User.id, User.email)
...     .where(User.email.isnotnull())
...     .aliased("active_users")
... )
>>> cte_b = (
...     Post
...     .select(Post.id, Post.user_id)
...     .where(Post.id > 0)
...     .aliased("recent_posts")
... )
>>> q = With(
...     cte_a, cte_b,
...     query=Comment.select(Comment.id, Comment.post_id).join(cte_b, on=Comment.post_id == cte_b.id),
... )
>>> q.build()
('WITH "active_users" AS (SELECT "users"."id","users"."email" FROM "public"."users" WHERE "users"."email" IS NOT NULL), "recent_posts" AS (SELECT "posts"."id","posts"."user_id" FROM "public"."posts" WHERE "posts"."id">$1) SELECT "comments"."id","comments"."post_id" FROM "public"."comments" JOIN "recent_posts" ON "comments"."post_id"="recent_posts"."id"', (0,))

```

### Recursive CTEs

```python
>>> q = With(cte_a, query=Post.select(Post.id), recursive=True)
>>> q.build()[0].startswith("WITH RECURSIVE")
True

```

---

## JSON output

### json() — row-level

Wrap the entire result row in `row_to_json`:

```python
>>> User.select(User.id, User.name).json().build()
('SELECT row_to_json(t) FROM (SELECT "users"."id","users"."name" FROM "public"."users") t', ())

```

Pass `raw=True` to cast the result to `::text`:

```python
>>> User.select(User.id, User.name).json(raw=True).build()
('SELECT row_to_json(t)::text FROM (SELECT "users"."id","users"."name" FROM "public"."users") t', ())

```

When executing via `AsyncConnection.fetch()`, norm auto-registers a JSON codec so the result is decoded into your `result_type` directly.

### prefetch() — nested JSON aggregation

`prefetch()` adds a lateral subquery that aggregates child rows as a JSON array:

```python
>>> posts_q = Post.select(Post.id, Post.title).aliased("posts")
>>> q = User.select(User.id, User.name).prefetch(posts_q)
>>> q.build()
('SELECT "users"."id","users"."name",(SELECT COALESCE(json_agg(t),\'[]\'::json) FROM (SELECT "posts"."id","posts"."title" FROM "public"."posts") t) AS "posts" FROM "public"."users"', ())

```

For a single-row prefetch (child limited to 1 row), norm emits `row_to_json` instead of `json_agg`:

```python
>>> latest_post = Post.select(Post.title).order_by(Post.id.desc()).limit(1).aliased("latest_post")
>>> User.select(User.id).prefetch(latest_post).build()
('SELECT "users"."id",(SELECT row_to_json(t) FROM (SELECT "posts"."title" FROM "public"."posts" ORDER BY "posts"."id" DESC LIMIT 1) t) AS "latest_post" FROM "public"."users"', ())

```

---

## Scalar subqueries

Use `.as_scalar()` to turn a query into a scalar subquery that can appear in a filter:

```python
>>> max_id_q = User.select(User.id.max()).as_scalar()
>>> Post.select(Post.id).where(Post.user_id == max_id_q).build()
('SELECT "posts"."id" FROM "public"."posts" WHERE "posts"."user_id"=(SELECT MAX("users"."id") FROM "public"."users")', ())

```

Scalar subqueries support all comparison operators (`==`, `!=`, `<`, `<=`, `>`, `>=`).

---

## Window functions

Chain `.over(*partition_by)` on a field to start a window spec, optionally `.order_by(...)`, then `.aliased("name")` to finalise:

```python
>>> row_num = EmpSalary.empno.over(EmpSalary.depname).order_by(EmpSalary.empno).aliased("row_num")
>>> EmpSalary.select(EmpSalary.empno, EmpSalary.depname, row_num).build()
('SELECT "empsalary"."empno","empsalary"."depname",ROW_NUMBER() OVER(PARTITION BY "empsalary"."depname" ORDER BY "empsalary"."empno") "row_num" FROM "public"."empsalary"', ())

```

Aggregate functions also support `.over()`:

```python
>>> running_total = EmpSalary.salary.sum().over(EmpSalary.depname).aliased("running_total")
>>> EmpSalary.select(EmpSalary.depname, EmpSalary.salary, running_total).build()
('SELECT "empsalary"."depname","empsalary"."salary",SUM("empsalary"."salary") OVER(PARTITION BY "empsalary"."depname") "running_total" FROM "public"."empsalary"', ())

```

Supported analytic functions via aggregation methods: `sum`, `min`, `max`, `avg`, `count`. `.over()` on a plain `Field` defaults to `ROW_NUMBER()`.

Sort direction inside the window:

```python
>>> EmpSalary.empno.over(EmpSalary.depname).order_by(EmpSalary.empno.desc()).aliased("rn").pika_field.get_sql(quote_char='"')
'ROW_NUMBER() OVER(PARTITION BY "empsalary"."depname" ORDER BY "empsalary"."empno" DESC)'

```

---

## aliased() on queries

`.aliased()` serves two purposes depending on context:

### Real table alias (no query state)

When called on a bare entity with no SELECT/WHERE/etc., it creates a SQL alias for the table — useful for self-joins:

```python
>>> Author = User.aliased("author")
>>> Post.select(Post.title, Author.name).join(Author, on=Post.user_id == Author.id).build()
('SELECT "posts"."title","author"."name" FROM "public"."posts" JOIN "public"."users" "author" ON "author"."id"="posts"."user_id"', ())

```

### Subquery alias (has query state)

When called on a query chain (`.select(...)` already called), it wraps the query as an inline subquery:

```python
>>> sub = User.select(User.id, User.name).where(User.id > 0).aliased("u")
>>> Post.select(Post.id, sub.id).join(sub, on=Post.user_id == sub.id).build()
('SELECT "posts"."id","u"."id" FROM "public"."posts" JOIN (SELECT "users"."id","users"."name" FROM "public"."users" WHERE "users"."id">$1) "u" ON "posts"."user_id"="u"."id"', (0,))

```

---

## Arithmetic

Fields support `+`, `-`, `*`, `/` with literals or other fields:

```python
>>> Post.select((Post.id + Post.user_id).aliased("combined")).build()
('SELECT "posts"."id"+"posts"."user_id" "combined" FROM "public"."posts"', ())

>>> Post.select((Post.id * 2).aliased("doubled")).build()
('SELECT "posts"."id"*$1 "doubled" FROM "public"."posts"', (2,))

```
