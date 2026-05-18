# 13 — Prefetch via JSON aggregation

Status: needs-triage
Type: AFK

## What to build

Add nested-prefetch support to `Selectable` via correlated JSON-aggregation subqueries. All prefetch declarations must compile into **one** SQL query — no N+1, no secondary round-trips, no separate prefetch builder class.

`msgspec.convert` must decode the resulting JSON column directly into the appropriate field on the parent result struct. No post-processing step is permitted.

This slice is PostgreSQL-only (uses `json_agg` / `row_to_json`). The dialect seam is preserved for a future MySQL / SQLite implementation, but only the Postgres path ships here.

## API design

`.prefetch()` accepts one or more aliased child queries. The child query is a fully self-contained `Selectable` chain — correlation condition lives in `.where()`, result column name comes from `.aliased()`, and the aggregation strategy is inferred from `.limit()`:

| Child has `.limit(1)` | SQL strategy | Decoded as |
|---|---|---|
| No | `COALESCE(json_agg(t), '[]'::json)` | `list[T]` |
| Yes | `row_to_json(t)` | `T \| None` |

No extra kwargs. No wrapper class. The aliased entity is stored directly in `__prefetches__`.

### Many (one-to-many) — no limit

```python
class CommentResult(msgspec.Struct):
    id: int
    body: str

class PostResult(msgspec.Struct):
    id: int
    title: str
    comments: list[CommentResult]

class UserResult(msgspec.Struct):
    id: int
    name: str
    email: str
    posts: list[PostResult]

q = (
    Users
    .select(Users.id, Users.name, Users.email)
    .prefetch(
        Posts
        .select(Posts.id, Posts.title)
        .where(Posts.user_id == Users.id)
        .prefetch(
            Comments
            .select(Comments.id, Comments.body)
            .where(Comments.post_id == Posts.id)
            .aliased("comments")
        )
        .aliased("posts")
    )
    .where(Users.age >= 18)
    .order_by(Users.name)
)

results: list[UserResult] = await conn.fetch(q, UserResult)
# results[0].posts[0].comments[0].body  ← fully nested, one round-trip
```

### Single (one-to-one) — `.limit(1)`

```python
class ProfileResult(msgspec.Struct):
    bio: str

class UserResult(msgspec.Struct):
    id: int
    name: str
    profile: ProfileResult | None

q = (
    Users
    .select(Users.id, Users.name)
    .prefetch(
        Profile
        .select(Profile.bio)
        .where(Profile.user_id == Users.id)
        .limit(1)
        .aliased("profile")
    )
)
```

### Generated SQL (two-level many example)

```sql
SELECT
    "users"."id",
    "users"."name",
    "users"."email",
    (
        SELECT COALESCE(json_agg(t), '[]'::json)
        FROM (
            SELECT
                "posts"."id",
                "posts"."title",
                (
                    SELECT COALESCE(json_agg(t), '[]'::json)
                    FROM (
                        SELECT "comments"."id", "comments"."body"
                        FROM "comments"
                        WHERE "comments"."post_id" = "posts"."id"
                    ) t
                ) AS "comments"
            FROM "posts"
            WHERE "posts"."user_id" = "users"."id"
        ) t
    ) AS "posts"
FROM "users"
WHERE "users"."age" >= $1
ORDER BY "users"."name" ASC
```

## Implementation notes

- Add `__prefetches__: tuple[type[Any], ...]` to `_QUERY_STATE_KEYS` and `_DEFAULTS` in `schema.py`
- Add `.prefetch(*children: type[Any]) -> type[Self]` to `Selectable` — each child must be aliased (has `__alias__` and `__inner__`)
- In `as_pypika()`, compile each prefetch as a raw SQL term appended to the SELECT column list:
  - If `child.__row_limit__ == 1` → `(SELECT row_to_json(t) FROM (...) t) AS "alias"`
  - Otherwise → `(SELECT COALESCE(json_agg(t), '[]'::json) FROM (...) t) AS "alias"`
- Child params share the parent's `params` list so placeholder indices are globally consistent
- No `PrefetchClause` wrapper — aliased entities are stored directly in `__prefetches__`

## Acceptance criteria

- [ ] `.prefetch(*children)` on `Selectable` accepts one or more aliased child queries and returns a new query
- [ ] Child query with no limit compiles to `COALESCE(json_agg(t), '[]'::json)` — decoded as `list[T]`
- [ ] Child query with `.limit(1)` compiles to `row_to_json(t)` — decoded as `T | None`
- [ ] Correlation condition lives in the child's `.where()` — no `fk`/`pk` kwargs on `.prefetch()`
- [ ] Result column name comes from `.aliased()` on the child — no `result_col` kwarg
- [ ] Prefetch is nestable to arbitrary depth by chaining `.prefetch()` before `.aliased()` on the child
- [ ] The compiled SQL contains exactly **one** statement; no follow-up queries are issued at execution time
- [ ] `msgspec.convert` decodes JSON columns directly into the nested struct fields — no manual JSON parsing
- [ ] Unit tests assert the full generated SQL string for: single-level many, single-level one-to-one, two-level nested, prefetch with filtered/ordered child
- [ ] End-to-end integration test against real PostgreSQL: two-level user → posts → comments returns the expected nested result tree
- [ ] No public API exists for fetching a prefetched relation in a separate query (N+1 must be structurally impossible)

## Blocked by

- 07 — Aggregations, GROUP BY, and HAVING
- 08 — Subqueries: `as_view()` and `as_scalar()`
