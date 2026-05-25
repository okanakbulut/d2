"""Integration tests for prefetch via JSON aggregation."""

from typing import Any

import msgspec
import pytest

from norm import db
from norm import AsyncConnection, Table, PrimaryKey, Field, TableMeta, field


class PfUsers(Table):
    __meta__ = TableMeta(table="pf_users", schema="public")
    id:   PrimaryKey[int] = field(default=db.serial())
    name: Field[str]


class PfPosts(Table):
    __meta__ = TableMeta(table="pf_posts", schema="public")
    id:      PrimaryKey[int] = field(default=db.serial())
    user_id: Field[int]
    title:   Field[str]


class PfComments(Table):
    __meta__ = TableMeta(table="pf_comments", schema="public")
    id:      PrimaryKey[int] = field(default=db.serial())
    post_id: Field[int]
    body:    Field[str]


class PfProfiles(Table):
    __meta__ = TableMeta(table="pf_profiles", schema="public")
    id:      PrimaryKey[int] = field(default=db.serial())
    user_id: Field[int]
    bio:     Field[str]


class PfScores(Table):
    __meta__ = TableMeta(table="pf_scores", schema="public")
    id:       PrimaryKey[int] = field(default=db.serial())
    user_id:  Field[int]
    category: Field[str]
    value:    Field[int]


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
    posts: list[PostResult]


class ProfileResult(msgspec.Struct):
    bio: str


class UserWithProfileResult(msgspec.Struct):
    id: int
    name: str
    profile: ProfileResult | None


class ScoreResult(msgspec.Struct):
    category: str
    value: int


class ScoreSummaryResult(msgspec.Struct):
    total: int | None
    average: float | None
    count: int


class SimplePostResult(msgspec.Struct):
    id: int
    title: str


class UserWithSiblingsResult(msgspec.Struct):
    id: int
    name: str
    posts: list[SimplePostResult]
    profile: ProfileResult | None


class UserWithScoresResult(msgspec.Struct):
    id: int
    name: str
    scores: list[ScoreResult]


class UserWithScoreSummaryResult(msgspec.Struct):
    id: int
    name: str
    score_summary: ScoreSummaryResult | None


class PostWithCommentCountResult(msgspec.Struct):
    id: int
    title: str
    comment_count: int


class UserWithCountedPostsResult(msgspec.Struct):
    id: int
    name: str
    posts: list[PostWithCommentCountResult]


class UserWithSimplePostsResult(msgspec.Struct):
    id: int
    name: str
    posts: list[SimplePostResult]


class PostWithCommentsResult(msgspec.Struct):
    id: int
    title: str
    comments: list[CommentResult]


class UserWithPostsAndProfileResult(msgspec.Struct):
    id: int
    name: str
    posts: list[PostWithCommentsResult]
    profile: ProfileResult | None


@pytest.fixture(autouse=True)
async def setup_tables(pg_conn: Any) -> None:
    await pg_conn.execute("""
        CREATE TABLE IF NOT EXISTS public.pf_users (
            id   SERIAL PRIMARY KEY,
            name TEXT NOT NULL
        )
    """)
    await pg_conn.execute("""
        CREATE TABLE IF NOT EXISTS public.pf_posts (
            id      SERIAL PRIMARY KEY,
            user_id INT NOT NULL REFERENCES public.pf_users(id),
            title   TEXT NOT NULL
        )
    """)
    await pg_conn.execute("""
        CREATE TABLE IF NOT EXISTS public.pf_comments (
            id      SERIAL PRIMARY KEY,
            post_id INT NOT NULL REFERENCES public.pf_posts(id),
            body    TEXT NOT NULL
        )
    """)
    await pg_conn.execute("""
        CREATE TABLE IF NOT EXISTS public.pf_profiles (
            id      SERIAL PRIMARY KEY,
            user_id INT NOT NULL REFERENCES public.pf_users(id),
            bio     TEXT NOT NULL
        )
    """)
    await pg_conn.execute("""
        CREATE TABLE IF NOT EXISTS public.pf_scores (
            id       SERIAL PRIMARY KEY,
            user_id  INT NOT NULL REFERENCES public.pf_users(id),
            category TEXT NOT NULL,
            value    INT NOT NULL
        )
    """)
    await pg_conn.execute("DELETE FROM public.pf_comments")
    await pg_conn.execute("DELETE FROM public.pf_posts")
    await pg_conn.execute("DELETE FROM public.pf_profiles")
    await pg_conn.execute("DELETE FROM public.pf_scores")
    await pg_conn.execute("DELETE FROM public.pf_users")


@pytest.mark.asyncio(loop_scope="session")
async def test_two_level_prefetch_returns_nested_tree(pg_conn: Any) -> None:
    alice_id = await pg_conn.fetchval(
        "INSERT INTO public.pf_users (name) VALUES ($1) RETURNING id", "Alice"
    )
    await pg_conn.fetchval(
        "INSERT INTO public.pf_users (name) VALUES ($1) RETURNING id", "Bob"
    )

    p1_id = await pg_conn.fetchval(
        "INSERT INTO public.pf_posts (user_id, title) VALUES ($1, $2) RETURNING id",
        alice_id, "First Post",
    )
    p2_id = await pg_conn.fetchval(
        "INSERT INTO public.pf_posts (user_id, title) VALUES ($1, $2) RETURNING id",
        alice_id, "Second Post",
    )

    await pg_conn.execute(
        "INSERT INTO public.pf_comments (post_id, body) VALUES ($1, $2)",
        p1_id, "Great post!",
    )
    await pg_conn.execute(
        "INSERT INTO public.pf_comments (post_id, body) VALUES ($1, $2)",
        p1_id, "Thanks for sharing",
    )
    await pg_conn.execute(
        "INSERT INTO public.pf_comments (post_id, body) VALUES ($1, $2)",
        p2_id, "Nice one",
    )

    q = (
        PfUsers
        .select(PfUsers.id, PfUsers.name)
        .order_by(PfUsers.name)
        .prefetch(
            PfPosts
            .select(PfPosts.id, PfPosts.title)
            .where(PfPosts.user_id == PfUsers.id)
            .order_by(PfPosts.title)
            .prefetch(
                PfComments
                .select(PfComments.id, PfComments.body)
                .where(PfComments.post_id == PfPosts.id)
                .order_by(PfComments.id)
                .aliased("comments")
            )
            .aliased("posts")
        )
    )

    conn = AsyncConnection(pg_conn)
    results = await conn.fetch(q, list[UserResult])

    assert len(results) == 2

    alice = results[0]
    assert alice.name == "Alice"
    assert len(alice.posts) == 2

    first_post = next(p for p in alice.posts if p.title == "First Post")
    assert len(first_post.comments) == 2
    comment_bodies = {c.body for c in first_post.comments}
    assert comment_bodies == {"Great post!", "Thanks for sharing"}

    second_post = next(p for p in alice.posts if p.title == "Second Post")
    assert len(second_post.comments) == 1
    assert second_post.comments[0].body == "Nice one"

    bob = results[1]
    assert bob.name == "Bob"
    assert bob.posts == []


@pytest.mark.asyncio(loop_scope="session")
async def test_one_to_one_prefetch_with_limit1(pg_conn: Any) -> None:
    user_id = await pg_conn.fetchval(
        "INSERT INTO public.pf_users (name) VALUES ($1) RETURNING id", "Carol"
    )
    await pg_conn.execute(
        "INSERT INTO public.pf_profiles (user_id, bio) VALUES ($1, $2)",
        user_id, "Software engineer",
    )
    await pg_conn.fetchval(
        "INSERT INTO public.pf_users (name) VALUES ($1) RETURNING id", "Dave"
    )

    q = (
        PfUsers
        .select(PfUsers.id, PfUsers.name)
        .order_by(PfUsers.name)
        .prefetch(
            PfProfiles
            .select(PfProfiles.bio)
            .where(PfProfiles.user_id == PfUsers.id)
            .limit(1)
            .aliased("profile")
        )
    )

    conn = AsyncConnection(pg_conn)
    results = await conn.fetch(q, list[UserWithProfileResult])

    carol = next(r for r in results if r.name == "Carol")
    assert carol.profile is not None
    assert carol.profile.bio == "Software engineer"

    dave = next(r for r in results if r.name == "Dave")
    assert dave.profile is None


@pytest.mark.asyncio(loop_scope="session")
async def test_multiple_siblings_prefetched_at_same_level(pg_conn: Any) -> None:
    """Two .prefetch() calls on the same parent produce two independent subquery columns."""
    eve_id = await pg_conn.fetchval(
        "INSERT INTO public.pf_users (name) VALUES ($1) RETURNING id", "Eve"
    )
    await pg_conn.fetchval(
        "INSERT INTO public.pf_users (name) VALUES ($1) RETURNING id", "Frank"
    )

    await pg_conn.execute(
        "INSERT INTO public.pf_posts (user_id, title) VALUES ($1, $2)",
        eve_id, "Eve's Post",
    )
    await pg_conn.execute(
        "INSERT INTO public.pf_profiles (user_id, bio) VALUES ($1, $2)",
        eve_id, "Writer",
    )

    q = (
        PfUsers
        .select(PfUsers.id, PfUsers.name)
        .order_by(PfUsers.name)
        .prefetch(
            PfPosts
            .select(PfPosts.id, PfPosts.title)
            .where(PfPosts.user_id == PfUsers.id)
            .aliased("posts")
        )
        .prefetch(
            PfProfiles
            .select(PfProfiles.bio)
            .where(PfProfiles.user_id == PfUsers.id)
            .limit(1)
            .aliased("profile")
        )
    )

    conn = AsyncConnection(pg_conn)
    results = await conn.fetch(q, list[UserWithSiblingsResult])

    eve = next(r for r in results if r.name == "Eve")
    assert len(eve.posts) == 1
    assert eve.posts[0].title == "Eve's Post"
    assert eve.profile is not None
    assert eve.profile.bio == "Writer"

    frank = next(r for r in results if r.name == "Frank")
    assert frank.posts == []
    assert frank.profile is None


@pytest.mark.asyncio(loop_scope="session")
async def test_prefetch_list_with_numeric_data(pg_conn: Any) -> None:
    """Prefetch a list of numeric rows — exercises json_agg over a scores table."""
    grace_id = await pg_conn.fetchval(
        "INSERT INTO public.pf_users (name) VALUES ($1) RETURNING id", "Grace"
    )
    hank_id = await pg_conn.fetchval(
        "INSERT INTO public.pf_users (name) VALUES ($1) RETURNING id", "Hank"
    )

    for category, value in [("math", 90), ("science", 85), ("art", 70)]:
        await pg_conn.execute(
            "INSERT INTO public.pf_scores (user_id, category, value) VALUES ($1, $2, $3)",
            grace_id, category, value,
        )
    await pg_conn.execute(
        "INSERT INTO public.pf_scores (user_id, category, value) VALUES ($1, $2, $3)",
        hank_id, "math", 55,
    )

    q = (
        PfUsers
        .select(PfUsers.id, PfUsers.name)
        .order_by(PfUsers.name)
        .prefetch(
            PfScores
            .select(PfScores.category, PfScores.value)
            .where(PfScores.user_id == PfUsers.id)
            .order_by(PfScores.category)
            .aliased("scores")
        )
    )

    conn = AsyncConnection(pg_conn)
    results = await conn.fetch(q, list[UserWithScoresResult])

    grace = next(r for r in results if r.name == "Grace")
    assert len(grace.scores) == 3
    score_map = {s.category: s.value for s in grace.scores}
    assert score_map == {"math": 90, "science": 85, "art": 70}

    hank = next(r for r in results if r.name == "Hank")
    assert len(hank.scores) == 1
    assert hank.scores[0].category == "math"
    assert hank.scores[0].value == 55


@pytest.mark.asyncio(loop_scope="session")
async def test_prefetch_aggregate_summary_via_limit1(pg_conn: Any) -> None:
    """Prefetch SUM/AVG/COUNT as a single summary row using limit(1) on an aggregate child."""
    ivan_id = await pg_conn.fetchval(
        "INSERT INTO public.pf_users (name) VALUES ($1) RETURNING id", "Ivan"
    )
    await pg_conn.fetchval(
        "INSERT INTO public.pf_users (name) VALUES ($1) RETURNING id", "Jane"
    )

    for value in [10, 20, 30]:
        await pg_conn.execute(
            "INSERT INTO public.pf_scores (user_id, category, value) VALUES ($1, $2, $3)",
            ivan_id, "quiz", value,
        )

    q = (
        PfUsers
        .select(PfUsers.id, PfUsers.name)
        .order_by(PfUsers.name)
        .prefetch(
            PfScores
            .select(
                PfScores.value.sum().aliased("total"),
                PfScores.value.avg().aliased("average"),
                PfScores.id.count().aliased("count"),
            )
            .where(PfScores.user_id == PfUsers.id)
            .limit(1)
            .aliased("score_summary")
        )
    )

    conn = AsyncConnection(pg_conn)
    results = await conn.fetch(q, list[UserWithScoreSummaryResult])

    ivan = next(r for r in results if r.name == "Ivan")
    assert ivan.score_summary is not None
    assert ivan.score_summary.total == 60
    assert ivan.score_summary.average == 20.0
    assert ivan.score_summary.count == 3

    # SUM/AVG over zero rows returns NULL (not a missing row), COUNT returns 0
    jane = next(r for r in results if r.name == "Jane")
    assert jane.score_summary is not None
    assert jane.score_summary.total is None
    assert jane.score_summary.average is None
    assert jane.score_summary.count == 0


@pytest.mark.asyncio(loop_scope="session")
async def test_prefetch_child_with_count_subcolumn(pg_conn: Any) -> None:
    """Child subquery mixes a regular column with a COUNT — posts with their comment count."""
    kate_id = await pg_conn.fetchval(
        "INSERT INTO public.pf_users (name) VALUES ($1) RETURNING id", "Kate"
    )

    p1_id = await pg_conn.fetchval(
        "INSERT INTO public.pf_posts (user_id, title) VALUES ($1, $2) RETURNING id",
        kate_id, "Popular Post",
    )
    await pg_conn.execute(
        "INSERT INTO public.pf_posts (user_id, title) VALUES ($1, $2)",
        kate_id, "Quiet Post",
    )

    for body in ["First!", "Second!", "Third!"]:
        await pg_conn.execute(
            "INSERT INTO public.pf_comments (post_id, body) VALUES ($1, $2)",
            p1_id, body,
        )

    q = (
        PfUsers
        .select(PfUsers.id, PfUsers.name)
        .prefetch(
            PfPosts
            .select(
                PfPosts.id,
                PfPosts.title,
                PfComments.id.count().aliased("comment_count"),
            )
            .where(PfPosts.user_id == PfUsers.id)
            .left_join(PfComments, on=PfComments.post_id == PfPosts.id)
            .group_by(PfPosts.id, PfPosts.title)
            .order_by(PfPosts.title)
            .aliased("posts")
        )
    )

    conn = AsyncConnection(pg_conn)
    results = await conn.fetch(q, list[UserWithCountedPostsResult])

    kate = next(r for r in results if r.name == "Kate")
    assert len(kate.posts) == 2

    popular = next(p for p in kate.posts if p.title == "Popular Post")
    assert popular.comment_count == 3

    quiet = next(p for p in kate.posts if p.title == "Quiet Post")
    assert quiet.comment_count == 0


@pytest.mark.asyncio(loop_scope="session")
async def test_prefetch_with_filtered_scores_above_threshold(pg_conn: Any) -> None:
    """Child WHERE clause filters rows before json_agg — only high scores included."""
    leo_id = await pg_conn.fetchval(
        "INSERT INTO public.pf_users (name) VALUES ($1) RETURNING id", "Leo"
    )

    for category, value in [("math", 95), ("science", 40), ("art", 88), ("history", 30)]:
        await pg_conn.execute(
            "INSERT INTO public.pf_scores (user_id, category, value) VALUES ($1, $2, $3)",
            leo_id, category, value,
        )

    q = (
        PfUsers
        .select(PfUsers.id, PfUsers.name)
        .prefetch(
            PfScores
            .select(PfScores.category, PfScores.value)
            .where(PfScores.user_id == PfUsers.id)
            .where(PfScores.value >= 80)
            .order_by(PfScores.category)
            .aliased("scores")
        )
    )

    conn = AsyncConnection(pg_conn)
    results = await conn.fetch(q, list[UserWithScoresResult])

    leo = next(r for r in results if r.name == "Leo")
    assert len(leo.scores) == 2
    categories = {s.category for s in leo.scores}
    assert categories == {"math", "art"}
    assert all(s.value >= 80 for s in leo.scores)


@pytest.mark.asyncio(loop_scope="session")
async def test_mixed_depth_siblings_prefetch(pg_conn: Any) -> None:
    """One sibling has its own nested child; the other doesn't — both compile in one query."""
    mia_id = await pg_conn.fetchval(
        "INSERT INTO public.pf_users (name) VALUES ($1) RETURNING id", "Mia"
    )
    await pg_conn.fetchval(
        "INSERT INTO public.pf_users (name) VALUES ($1) RETURNING id", "Ned"
    )

    p_id = await pg_conn.fetchval(
        "INSERT INTO public.pf_posts (user_id, title) VALUES ($1, $2) RETURNING id",
        mia_id, "Mia's Post",
    )
    await pg_conn.execute(
        "INSERT INTO public.pf_profiles (user_id, bio) VALUES ($1, $2)",
        mia_id, "Engineer",
    )
    await pg_conn.execute(
        "INSERT INTO public.pf_comments (post_id, body) VALUES ($1, $2)",
        p_id, "Nice write-up",
    )

    q = (
        PfUsers
        .select(PfUsers.id, PfUsers.name)
        .order_by(PfUsers.name)
        .prefetch(
            PfPosts
            .select(PfPosts.id, PfPosts.title)
            .where(PfPosts.user_id == PfUsers.id)
            .prefetch(
                PfComments
                .select(PfComments.id, PfComments.body)
                .where(PfComments.post_id == PfPosts.id)
                .aliased("comments")
            )
            .aliased("posts")
        )
        .prefetch(
            PfProfiles
            .select(PfProfiles.bio)
            .where(PfProfiles.user_id == PfUsers.id)
            .limit(1)
            .aliased("profile")
        )
    )

    conn = AsyncConnection(pg_conn)
    results = await conn.fetch(q, list[UserWithPostsAndProfileResult])

    mia = next(r for r in results if r.name == "Mia")
    assert len(mia.posts) == 1
    assert mia.posts[0].title == "Mia's Post"
    assert len(mia.posts[0].comments) == 1
    assert mia.posts[0].comments[0].body == "Nice write-up"
    assert mia.profile is not None
    assert mia.profile.bio == "Engineer"

    ned = next(r for r in results if r.name == "Ned")
    assert ned.posts == []
    assert ned.profile is None


@pytest.mark.asyncio(loop_scope="session")
async def test_outer_where_does_not_break_prefetch_correlation(pg_conn: Any) -> None:
    """Outer WHERE filters which parents appear; each surviving parent still gets its own children."""
    for name in ["Olivia", "Pat", "Quinn"]:
        uid = await pg_conn.fetchval(
            "INSERT INTO public.pf_users (name) VALUES ($1) RETURNING id", name
        )
        if name != "Pat":
            await pg_conn.execute(
                "INSERT INTO public.pf_posts (user_id, title) VALUES ($1, $2)",
                uid, f"{name}'s Post",
            )

    q = (
        PfUsers
        .select(PfUsers.id, PfUsers.name)
        .where(PfUsers.name != "Quinn")
        .order_by(PfUsers.name)
        .prefetch(
            PfPosts
            .select(PfPosts.id, PfPosts.title)
            .where(PfPosts.user_id == PfUsers.id)
            .aliased("posts")
        )
    )

    conn = AsyncConnection(pg_conn)
    results = await conn.fetch(q, list[UserWithSimplePostsResult])

    assert len(results) == 2
    names = [r.name for r in results]
    assert "Quinn" not in names

    olivia = next(r for r in results if r.name == "Olivia")
    assert len(olivia.posts) == 1
    assert olivia.posts[0].title == "Olivia's Post"

    pat = next(r for r in results if r.name == "Pat")
    assert pat.posts == []
