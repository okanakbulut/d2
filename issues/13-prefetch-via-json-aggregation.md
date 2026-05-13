# 13 — Prefetch via JSON aggregation

Status: needs-triage
Type: AFK

## What to build

Add nested-prefetch support to `QueryBuilder` via correlated JSON-aggregation subqueries. All prefetch declarations must compile into **one** SQL query — no N+1, no secondary round-trips, no separate prefetch builder class.

`msgspec.convert` must decode the resulting JSON-aggregated column directly into a `list[ChildResultStruct]` field on the parent result struct. No post-processing step is permitted.

This slice is PostgreSQL-only (uses `json_agg`). The dialect seam is preserved for a future MySQL / SQLite implementation, but only the Postgres path ships here.

### Usage example

```python
class CommentResult(msgspec.Struct):
    id: int
    body: str

class PostResult(msgspec.Struct):
    id: int
    title: str
    comments: list[CommentResult]          # populated from JSON column

class UserResult(msgspec.Struct):
    id: int
    name: str
    email: str
    posts: list[PostResult]                # populated from JSON column

q = (
    Users
    .select(Users.id, Users.name, Users.email)
    .prefetch(
        Posts,
        fk=Posts.user_id,
        pk=Users.id,
        result_col="posts",
        child_select=(
            Posts
            .select(Posts.id, Posts.title)
            .prefetch(
                Comments,
                fk=Comments.post_id,
                pk=Posts.id,
                result_col="comments",
                child_select=Comments.select(Comments.id, Comments.body),
            )
        ),
    )
    .where(Users.age >= 18)
    .order_by(Users.name)
)

results: list[UserResult] = await conn.fetch(q, UserResult)
# results[0].posts[0].comments[0].body  ← fully nested, one round-trip
```

## Acceptance criteria

- [ ] `QueryBuilder.prefetch(child_proxy, *, fk: FieldProxy, pk: FieldProxy, result_col: str, child_select: QueryBuilder | None = None)` returns a new `QueryBuilder`
- [ ] When `child_select` is omitted, `child_proxy.select_all()` is used
- [ ] Prefetch is nestable to arbitrary depth: a `child_select` argument may itself contain `.prefetch(...)` calls
- [ ] The compiled SQL contains exactly **one** statement; no follow-up queries are issued at execution time
- [ ] The correlated subquery joins the child rows to the parent via `fk == pk`
- [ ] The aggregated column is named `result_col` and rendered using the PostgreSQL `json_agg` function (the dialect seam keeps room for other backends, but only Postgres is shipped)
- [ ] `msgspec.convert` decodes the JSON column directly into the nested struct list — no manual JSON parsing in user code
- [ ] Unit tests assert the generated SQL structure for: single-level prefetch, two-level prefetch, prefetch with a filtered/ordered/column-projected `child_select`
- [ ] End-to-end integration test against real PostgreSQL: a two-level user → posts → comments fetch returns the expected nested result tree
- [ ] No public API exists for fetching the prefetched relation in a separate query (per NF5 — N+1 must be structurally impossible)

## Blocked by

- 07 — Aggregations, GROUP BY, and HAVING
- 08 — Subqueries: `as_view()` and `as_scalar()`
