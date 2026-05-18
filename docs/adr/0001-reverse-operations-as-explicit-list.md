# Migration reversal via an explicit `reverse_operations` list

Each `Migration` carries two lists — `operations` (forward) and `reverse_operations` (backward) — both written by codegen at `make` time when full schema state is known. Rollback executes `reverse_operations` literally; no operation knows how to invert itself.

## Considered alternatives

- **Per-op `reverse(state_before) -> Operation | None`.** Each op derives its inverse from the schema state captured immediately before it was applied. Rejected because (a) it pushes state-replay plumbing into the runner, (b) destructive ops like `DropColumn` need full `ColumnState` reconstruction that codegen already has cheaply at generation time, and (c) hand-editing complex rollbacks is awkward when the inverse is a method on an opaque op class.
- **Replay-to-previous-state rollback.** Replay migrations 1..N-1 into a fresh state, diff against current, apply that diff. Rejected because data-bearing ops would re-execute in unintended ways and the user can't preview what rollback will run.

## Consequences

- Codegen must materialize the full reverse path for every diff entry at generation time. The migration file is the single record of what runs in both directions.
- A migration with `reverse_operations = None` is explicitly non-reversible; rollback raises pointing at the file. `reverse_operations = []` means "no-op reverse" (e.g., for backfill-only migrations).
