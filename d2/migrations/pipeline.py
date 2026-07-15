"""Schema diff pipeline: replay → snapshot → diff."""

from dataclasses import dataclass
from pathlib import Path

from .draft import diff_states
from .operations import Operation
from .replay import replay_migrations
from .snapshot import models_to_schema_state
from .state import SchemaState


@dataclass
class SchemaPipeline:
    current: SchemaState
    target: SchemaState
    forward: list[Operation]
    reverse: list[Operation]

    @classmethod
    def from_states(cls, current: SchemaState, target: SchemaState) -> SchemaPipeline:
        forward, reverse = diff_states(current, target)
        return cls(current=current, target=target, forward=forward, reverse=reverse)

    @classmethod
    def build(cls, *, migration_files: list[Path], models: list[type]) -> SchemaPipeline:
        current = replay_migrations(migration_files)
        target = models_to_schema_state(models)
        return cls.from_states(current, target)

    @property
    def has_changes(self) -> bool:
        return bool(self.forward)
