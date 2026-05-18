"""Unit tests for prefetch via JSON aggregation."""

from .conftest import Users, Posts, Comments, Profiles


class TestPrefetchWithFilteredOrderedChild:
    def test_child_with_order_by(self):
        q = (
            Users
            .select(Users.id, Users.name)
            .prefetch(
                Posts
                .select(Posts.id, Posts.title)
                .where(Posts.user_id == Users.id)
                .order_by(Posts.title)
                .aliased("posts")
            )
        )
        sql, params = q.build()
        assert sql == (
            'SELECT "users"."id","users"."name",'
            '(SELECT COALESCE(json_agg(t),\'[]\'::json) FROM'
            ' (SELECT "posts"."id","posts"."title" FROM "public"."posts"'
            ' WHERE "users"."id"="posts"."user_id"'
            ' ORDER BY "posts"."title" ASC) t) AS "posts"'
            ' FROM "public"."users"'
        )
        assert params == ()

    def test_outer_where_and_child_prefetch(self):
        q = (
            Users
            .select(Users.id, Users.name, Users.email)
            .where(Users.age >= 18)
            .order_by(Users.name)
            .prefetch(
                Posts
                .select(Posts.id, Posts.title)
                .where(Posts.user_id == Users.id)
                .aliased("posts")
            )
        )
        sql, params = q.build()
        assert sql == (
            'SELECT "users"."id","users"."name","users"."email",'
            '(SELECT COALESCE(json_agg(t),\'[]\'::json) FROM'
            ' (SELECT "posts"."id","posts"."title" FROM "public"."posts"'
            ' WHERE "users"."id"="posts"."user_id") t) AS "posts"'
            ' FROM "public"."users"'
            ' WHERE "users"."age">=$1'
            ' ORDER BY "users"."name" ASC'
        )
        assert params == (18,)

    def test_params_are_shared_across_child(self):
        q = (
            Users
            .select(Users.id)
            .where(Users.age >= 18)
            .prefetch(
                Posts
                .select(Posts.id)
                .where(Posts.user_id == Users.id)
                .where(Posts.title == "hello")
                .aliased("posts")
            )
        )
        sql, params = q.build()
        assert '"posts"."title"=$1' in sql
        assert '"users"."age">=$2' in sql
        assert params == ("hello", 18)


class TestPrefetchTwoLevelNested:
    def test_two_level_many_nested(self):
        q = (
            Users
            .select(Users.id, Users.name)
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
        )
        sql, params = q.build()
        assert sql == (
            'SELECT "users"."id","users"."name",'
            '(SELECT COALESCE(json_agg(t),\'[]\'::json) FROM'
            ' (SELECT "posts"."id","posts"."title",'
            '(SELECT COALESCE(json_agg(t),\'[]\'::json) FROM'
            ' (SELECT "comments"."id","comments"."body" FROM "public"."comments"'
            ' WHERE "posts"."id"="comments"."post_id") t) AS "comments"'
            ' FROM "public"."posts"'
            ' WHERE "users"."id"="posts"."user_id") t) AS "posts"'
            ' FROM "public"."users"'
        )
        assert params == ()


class TestPrefetchSingleLevelOneToOne:
    def test_limit1_generates_row_to_json(self):
        q = (
            Users
            .select(Users.id, Users.name)
            .prefetch(
                Profiles
                .select(Profiles.bio)
                .where(Profiles.user_id == Users.id)
                .limit(1)
                .aliased("profile")
            )
        )
        sql, params = q.build()
        assert sql == (
            'SELECT "users"."id","users"."name",'
            '(SELECT row_to_json(t) FROM'
            ' (SELECT "profiles"."bio" FROM "public"."profiles"'
            ' WHERE "users"."id"="profiles"."user_id" LIMIT 1) t) AS "profile"'
            ' FROM "public"."users"'
        )
        assert params == ()


class TestPrefetchSingleLevelMany:
    def test_single_level_many_generates_json_agg(self):
        q = (
            Users
            .select(Users.id, Users.name)
            .prefetch(
                Posts
                .select(Posts.id, Posts.title)
                .where(Posts.user_id == Users.id)
                .aliased("posts")
            )
        )
        sql, params = q.build()
        assert sql == (
            'SELECT "users"."id","users"."name",'
            '(SELECT COALESCE(json_agg(t),\'[]\'::json) FROM'
            ' (SELECT "posts"."id","posts"."title" FROM "public"."posts"'
            ' WHERE "users"."id"="posts"."user_id") t) AS "posts"'
            ' FROM "public"."users"'
        )
        assert params == ()
