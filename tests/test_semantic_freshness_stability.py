import inspect

from backend.database.discovery_service import SchemaDiscoveryService


def test_sample_value_query_has_deterministic_ordering():
    source = SchemaDiscoveryService()
    # The query is generated in the service; this regression protects the
    # fingerprint from changing merely because PostgreSQL returned rows in a
    # different physical order.
    assert "ORDER BY {quoted_column} ASC" in inspect.getsource(
        source.get_column_sample_values
    )
