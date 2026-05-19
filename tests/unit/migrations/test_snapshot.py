"""Unit tests for snapshot: models → SchemaState."""

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from norm.migrations.snapshot import models_to_schema_state
from norm.model import TableMeta, field
from norm.schema import Field, PrimaryKey, Table, View


class TestModelsToSchemaState:
    def test_simple_table_one_column(self):
        class SnapWidget(Table):
            label: Field[str]

        state = models_to_schema_state([SnapWidget])

        assert list(state.tables.keys()) == ["snap_widget"]
        t = state.tables["snap_widget"]
        assert list(t.columns.keys()) == ["label"]
        col = t.columns["label"]
        assert col.type == "TEXT"
        assert col.nullable is False
        assert col.primary_key is False
        assert col.has_sequence_default is False

    def test_bigserial_for_pk_with_db_default(self):
        class SnapOrder(Table):
            id: PrimaryKey[int] = field(db_default=True)

        state = models_to_schema_state([SnapOrder])
        col = state.tables["snap_order"].columns["id"]
        # Per ADR-0004, state stores BIGINT + has_sequence_default
        assert col.type == "BIGINT"
        assert col.primary_key is True
        assert col.nullable is False
        assert col.has_sequence_default is True

    def test_plain_int_maps_to_bigint(self):
        class SnapCounter(Table):
            n: Field[int]

        col = models_to_schema_state([SnapCounter]).tables["snap_counter"].columns["n"]
        assert col.type == "BIGINT"
        assert col.has_sequence_default is False

    def test_full_type_mapping(self):
        class SnapKitchenSink(Table):
            i: Field[int]
            s: Field[str]
            f: Field[float]
            b: Field[bool]
            dt: Field[datetime]
            d: Field[date]
            dec: Field[Decimal]
            u: Field[UUID]
            j_dict: Field[dict[str, object]]
            j_list: Field[list[object]]
            blob: Field[bytes]

        cols = models_to_schema_state([SnapKitchenSink]).tables["snap_kitchen_sink"].columns
        assert cols["i"].type == "BIGINT"
        assert cols["s"].type == "TEXT"
        assert cols["f"].type == "DOUBLE PRECISION"
        assert cols["b"].type == "BOOLEAN"
        assert cols["dt"].type == "TIMESTAMPTZ"
        assert cols["d"].type == "DATE"
        assert cols["dec"].type == "NUMERIC"
        assert cols["u"].type == "UUID"
        assert cols["j_dict"].type == "JSONB"
        assert cols["j_list"].type == "JSONB"
        assert cols["blob"].type == "BYTEA"

    def test_optional_field_is_nullable(self):
        class SnapMaybe(Table):
            name: Field[str | None]

        col = models_to_schema_state([SnapMaybe]).tables["snap_maybe"].columns["name"]
        assert col.type == "TEXT"
        assert col.nullable is True

    def test_views_are_skipped(self):
        class SnapVisibleThing(View):
            id: Field[int]

        state = models_to_schema_state([SnapVisibleThing])
        assert state.tables == {}


class TestSnapshotExtensionsAndSchemas:
    def test_extensions_unioned_across_models(self):
        class SnapA(Table):
            __meta__ = TableMeta(extensions=("pgcrypto",))
            x: Field[str]

        class SnapB(Table):
            __meta__ = TableMeta(extensions=("uuid-ossp", "pgcrypto"))
            y: Field[str]

        state = models_to_schema_state([SnapA, SnapB])
        assert state.extensions == {"pgcrypto", "uuid-ossp"}

    def test_schemas_collected_from_meta_excluding_public_and_none(self):
        class SnapAuditEvent(Table):
            __meta__ = TableMeta(schema="audit")
            x: Field[str]

        class SnapReport(Table):
            __meta__ = TableMeta(schema="reporting")
            y: Field[str]

        class SnapPublic(Table):
            __meta__ = TableMeta(schema="public")
            z: Field[str]

        class SnapNoSchema(Table):
            w: Field[str]

        state = models_to_schema_state(
            [SnapAuditEvent, SnapReport, SnapPublic, SnapNoSchema]
        )
        assert state.schemas == {"audit", "reporting"}

    def test_no_extensions_or_schemas_when_unset(self):
        class SnapPlain(Table):
            x: Field[str]

        state = models_to_schema_state([SnapPlain])
        assert state.extensions == set()
        assert state.schemas == set()
