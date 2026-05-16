"""Shared models for unit tests."""

from norm import TableMeta, Field, PrimaryKey, Unique, Index, Table, field


class Users(Table):
    __meta__ = TableMeta(schema="public")
    id:         PrimaryKey[int] = field(db_default=True)
    name:       Index[str]
    email:      Unique[str]
    age:        Field[int]
    created_at: Field[str]


class UserModelExplicit(Table):
    __meta__ = TableMeta(table="accounts_user", schema="public")
    id:    PrimaryKey[int]
    name:  Field[str]


class Posts(Table):
    __meta__ = TableMeta(schema="public")
    id:      PrimaryKey[int] = field(db_default=True)
    user_id: Field[int]
    title:   Field[str]


class Orders(Table):
    __meta__ = TableMeta(schema="public")
    id:      PrimaryKey[int] = field(db_default=True)
    user_id: Field[int]
    amount:  Field[int]


class Employees(Table):
    __meta__ = TableMeta(schema="public")
    id:         PrimaryKey[int] = field(db_default=True)
    name:       Field[str]
    manager_id: Field[int]
