"""Unit tests for the model registry."""

from norm.migrations.registry import _MODEL_REGISTRY, collect_models
from norm.schema import Field, Table, View


class TestRegistryRegistration:
    def test_table_subclass_registered_under_module_qualname(self):
        class RegUser(Table):
            id: Field[int]

        key = f"{RegUser.__module__}.{RegUser.__qualname__}"
        assert key in _MODEL_REGISTRY
        assert _MODEL_REGISTRY[key] is RegUser

    def test_view_subclass_registered(self):
        class RegActiveUser(View):
            id: Field[int]

        key = f"{RegActiveUser.__module__}.{RegActiveUser.__qualname__}"
        assert key in _MODEL_REGISTRY
        assert _MODEL_REGISTRY[key] is RegActiveUser

    def test_clone_does_not_register(self):
        class RegOrder(Table):
            id: Field[int]

        before = dict(_MODEL_REGISTRY)
        RegOrder.clone()
        assert _MODEL_REGISTRY == before

    def test_aliased_does_not_register(self):
        class RegItem(Table):
            id: Field[int]

        before = dict(_MODEL_REGISTRY)
        RegItem.aliased("i")
        assert _MODEL_REGISTRY == before

    def test_set_op_does_not_register(self):
        class RegA(Table):
            id: Field[int]

        class RegB(Table):
            id: Field[int]

        before = dict(_MODEL_REGISTRY)
        RegA.union(RegB)
        assert _MODEL_REGISTRY == before


class TestCollectModels:
    def test_returns_registered_models(self):
        class CMThing(Table):
            id: Field[int]

        assert CMThing in collect_models()
