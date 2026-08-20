import inspect

from backend.database.discovery_service import SchemaDiscoveryService


def test_sample_value_query_has_deterministic_ordering():
    source = SchemaDiscoveryService()
    assert "ORDER BY {quoted_column} ASC" in inspect.getsource(
        source.get_column_sample_values
    )
