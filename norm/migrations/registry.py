"""Model registry — populated by `NormMeta.__new__` for declared models.

The registry is keyed by `f"{cls.__module__}.{cls.__qualname__}"`. Only models
that hit the `_setup_table` path register (i.e. those without a pre-supplied
`__table__` in the class namespace). Clones, aliases, and set-op composites
short-circuit before reaching the registry.
"""

MODEL_REGISTRY: dict[str, type] = {}


def register(cls: type) -> None:
    """Register a model class under ``f"{module}.{qualname}"``."""
    key = f"{cls.__module__}.{cls.__qualname__}"
    MODEL_REGISTRY[key] = cls


def collect_models() -> list[type]:
    """Return all registered models in insertion order."""
    return list(MODEL_REGISTRY.values())


# Backwards-compatible aliases — kept so external imports keep working.
_MODEL_REGISTRY = MODEL_REGISTRY
_register = register
