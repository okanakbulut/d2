# Writes

```python
>>> from norm import Table, Field, PrimaryKey, Unique, field, excluded, db
>>> class User(Table):
...     id:       PrimaryKey[int] = field(default=db.serial())
...     username: Unique[str]
...     email:    Unique[str]
...
>>> class Post(Table):
...     id:      PrimaryKey[int] = field(default=db.serial())
...     user_id: Field[int]
...     title:   Field[str]
...     body:    Field[str | None]
...

```

## INSERT

### Single row

Pass column values as keyword arguments:

```python
>>> q = User.insert(username="alice", email="alice@example.com")
>>> q.build()
('INSERT INTO "public"."users" ("username","email") VALUES ($1,$2)', ('alice', 'alice@example.com'))

```

Columns marked `db_default=True` or typed `PrimaryKey` are excluded automatically. Pass `exclude_defaults=False` to include them:

```python
>>> User.insert(id=42, username="alice", email="alice@example.com", exclude_defaults=False).build()
('INSERT INTO "public"."users" ("id","username","email") VALUES ($1,$2,$3)', (42, 'alice', 'alice@example.com'))

```

### Multiple rows

Pass a list of dicts. All dicts must have the same keys:

```python
>>> rows = [
...     {"username": "alice", "email": "alice@example.com"},
...     {"username": "bob",   "email": "bob@example.com"},
... ]
>>> User.insert(rows).build()
('INSERT INTO "public"."users" ("username","email") VALUES ($1,$2)', [('alice', 'alice@example.com'), ('bob', 'bob@example.com')])

```

Use `conn.execute_many(q)` for bulk inserts (see [Connection](connection.md)).

### returning

Get columns back from an insert:

```python
>>> User.insert(username="alice", email="alice@example.com").returning(User.id).build()
('INSERT INTO "public"."users" ("username","email") VALUES ($1,$2) RETURNING "users"."id"', ('alice', 'alice@example.com'))

```

---

## on_conflict (upsert)

Chain `.on_conflict(*target_fields)` after `.insert()` to build an `ON CONFLICT` clause.

### do_nothing

```python
>>> q = (
...     User
...     .insert(username="alice", email="alice@example.com")
...     .on_conflict(User.email)
...     .do_nothing()
... )
>>> q.build()
('INSERT INTO "public"."users" ("username","email") VALUES ($1,$2) ON CONFLICT ("email") DO NOTHING', ('alice', 'alice@example.com'))

```

### do_update

```python
>>> q = (
...     User
...     .insert(username="alice", email="alice@example.com")
...     .on_conflict(User.email)
...     .do_update(username="alice_updated", email=excluded(User.email))
...     .returning(User.id, User.username)
... )
>>> q.build()
('INSERT INTO "public"."users" ("username","email") VALUES ($1,$2) ON CONFLICT ("email") DO UPDATE SET "username"=$3, "email"=EXCLUDED."email" RETURNING "users"."id","users"."username"', ('alice', 'alice@example.com', 'alice_updated'))

```

`excluded(field)` renders as `EXCLUDED."column"` — the value that was rejected by the conflict. Use it to refer to the incoming row in the `DO UPDATE SET` clause.

`do_update` / `update` are aliases for the same method.

---

## UPDATE

```python
>>> User.update(username="bob").where(User.id == 1).build()
('UPDATE "public"."users" SET "username"=$1 WHERE "users"."id"=$2', ('bob', 1))

```

Multiple `.where()` calls are ANDed together:

```python
>>> q = (
...     User
...     .update(username="bob", email="bob@example.com")
...     .where(User.id > 0)
...     .where(User.email.isnotnull())
... )
>>> q.build()
('UPDATE "public"."users" SET "username"=$1,"email"=$2 WHERE "users"."id">$3 AND "users"."email" IS NOT NULL', ('bob', 'bob@example.com', 0))

```

Assign a field value to another field (column-to-column update):

```python
>>> Post.update(title=Post.body).where(Post.id == 1).build()
('UPDATE "public"."posts" SET "title"="posts"."body" WHERE "posts"."id"=$1', (1,))

```

---

## DELETE

```python
>>> User.delete().where(User.id == 99).build()
('DELETE FROM "public"."users" WHERE "users"."id"=$1', (99,))

```

Without a `.where()` the DELETE will affect every row. Norm does not add any safety guard — always filter.
