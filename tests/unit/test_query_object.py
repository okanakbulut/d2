"""A query under construction is a value, not a class.

Every builder step used to call ``Selectable.clone()``, which built a whole new
Python class through ``D2Meta`` -- ~6us of ``type.__new__`` per ``.where()``,
72% of the step's cost. Worse, ``clone()`` passed ``bases=(cls,)``, so each step
subclassed the one before it and the MRO grew with the chain: a 20-field table
cost 6.5us at the first step and 9.4us at the eighth.

Query state now lives in a ``Query`` struct beside the entity rather than in
dunders on a subclass of it, so a step is one ``msgspec.structs.replace``.

The SQL these produce is covered by the rest of the suite; what is pinned here
is the shape of the object, because that is what the cost follows from.
"""

from d2.schema import Query

from .conftest import Users


def _chain():
    return Users.select(Users.id).where(Users.age > 18).order_by(Users.name)


def test_a_builder_step_returns_a_value_not_a_class():
    assert not isinstance(_chain(), type)
    assert isinstance(_chain(), Query)


def test_chaining_does_not_deepen_the_type_hierarchy():
    """The old clone() subclassed per step, so cost grew with chain length."""
    one = Users.select(Users.id)
    many = one
    for _ in range(10):
        many = many.where(Users.id == 1)

    assert type(many) is type(one)


def test_every_entry_point_starts_a_query():
    """Not just select(): the entity exposes the whole builder."""
    for start in (
        Users.select(Users.id),
        Users.select_all(),
        Users.where(Users.id == 1),
        Users.order_by(Users.name),
        Users.limit(5),
        Users.offset(5),
        Users.distinct(),
        Users.group_by(Users.age),
    ):
        assert isinstance(start, Query), start


def test_a_step_does_not_mutate_the_query_it_came_from():
    base = Users.select(Users.id)
    narrowed = base.where(Users.age > 18)

    assert base.filters == ()
    assert len(narrowed.filters) == 1


def test_the_entity_is_carried_not_copied():
    """Fields stay on the table, so a step never re-copies 20 Field proxies."""
    q = Users.select(Users.id).where(Users.age > 18)

    assert q.entity is Users
