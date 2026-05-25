"""Shared models for unit tests."""

from norm import TableMeta, Field, PrimaryKey, Unique, Index, Table, db, field


class Users(Table):
    __meta__ = TableMeta(table="users", schema="public")
    id:         PrimaryKey[int] = field(default=db.serial())
    name:       Index[str]
    email:      Unique[str]
    age:        Field[int]
    created_at: Field[str]


class UserModelExplicit(Table):
    __meta__ = TableMeta(table="accounts_user", schema="public")
    id:    PrimaryKey[int]
    name:  Field[str]


class Posts(Table):
    __meta__ = TableMeta(table="posts", schema="public")
    id:      PrimaryKey[int] = field(default=db.serial())
    user_id: Field[int]
    title:   Field[str]


class Comments(Table):
    __meta__ = TableMeta(table="comments", schema="public")
    id:      PrimaryKey[int] = field(default=db.serial())
    post_id: Field[int]
    body:    Field[str]


class Profiles(Table):
    __meta__ = TableMeta(table="profiles", schema="public")
    id:      PrimaryKey[int] = field(default=db.serial())
    user_id: Field[int]
    bio:     Field[str]


class Orders(Table):
    __meta__ = TableMeta(table="orders", schema="public")
    id:      PrimaryKey[int] = field(default=db.serial())
    user_id: Field[int]
    amount:  Field[int]


class Employees(Table):
    __meta__ = TableMeta(table="employees", schema="public")
    id:         PrimaryKey[int] = field(default=db.serial())
    name:       Field[str]
    manager_id: Field[int]


class EmpSalary(Table):
    __meta__ = TableMeta(table="empsalary", schema="public")
    depname: Field[str]
    empno:   Field[int]
    salary:  Field[int]
