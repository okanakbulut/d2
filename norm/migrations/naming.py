"""Auto-naming for indexes and unique constraints with identifier-length checks.

Postgres truncates identifiers > 63 chars; we refuse silently-truncated names
and tell the user to pass an explicit `name=`.
"""

PG_IDENTIFIER_LIMIT = 63


class IdentifierTooLongError(ValueError):
    """Raised when an auto-generated identifier exceeds the Postgres limit."""


def _check(name: str, *, table: str, columns: tuple[str, ...]) -> str:
    if len(name) > PG_IDENTIFIER_LIMIT:
        raise IdentifierTooLongError(
            f"auto-generated identifier {name!r} is "
            f"{len(name)} chars (> {PG_IDENTIFIER_LIMIT}); "
            f"pass an explicit name= for columns {columns!r} on {table!r}"
        )
    return name


def auto_index_name(table: str, columns: tuple[str, ...]) -> str:
    name = f"idx_{table}_{'_'.join(columns)}"
    return _check(name, table=table, columns=columns)


def auto_unique_name(table: str, columns: tuple[str, ...]) -> str:
    name = f"{table}_{'_'.join(columns)}_key"
    return _check(name, table=table, columns=columns)


def auto_fk_name(table: str, columns: tuple[str, ...]) -> str:
    name = f"{table}_{'_'.join(columns)}_fkey"
    return _check(name, table=table, columns=columns)
