import hashlib
import json
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional

from sqlalchemy import text

from backend.config import get_settings
from backend.database.connection import db_connection
from backend.database.models import (
    ColumnSampleValue,
    DiscoveredColumnInfo,
    DiscoveredTableInfo,
    ForeignKeyInfo,
    IndexInfo,
    RelationshipInfo,
    SchemaDiscoveryResponse,
    SchemaDiscoverySnapshot,
)


TEXT_LIKE_TYPES = {
    "character varying",
    "character",
    "text",
    "USER-DEFINED",
}


class SchemaDiscoveryService:
    def __init__(self):
        self.settings = get_settings()
        self.connection = db_connection
        self.schema_root = Path(__file__).parent.parent.parent / "schema" / "tenants"

    def _quote_identifier(self, identifier: str) -> str:
        return '"' + identifier.replace('"', '""') + '"'

    def _qualified_table(self, schema_name: str, table_name: str) -> str:
        return f"{self._quote_identifier(schema_name)}.{self._quote_identifier(table_name)}"

    def _json_safe(self, value: Any) -> Any:
        if isinstance(value, (datetime, date)):
            return value.isoformat()
        if isinstance(value, Decimal):
            return float(value)
        return value

    def _tenant_dir(self, tenant_id: str) -> Path:
        tenant_dir = self.schema_root / tenant_id
        tenant_dir.mkdir(parents=True, exist_ok=True)
        return tenant_dir

    def get_tables(self, schema_name: str = "public") -> List[Dict[str, Any]]:
        query = """
            SELECT
                t.table_schema,
                t.table_name,
                obj_description(format('%I.%I', t.table_schema, t.table_name)::regclass) AS table_comment
            FROM information_schema.tables t
            WHERE t.table_schema = :schema_name
              AND t.table_type = 'BASE TABLE'
            ORDER BY t.table_name
        """
        result = self.connection.execute_query(query, {"schema_name": schema_name})
        return [
            {
                "schema_name": row[0],
                "name": row[1],
                "comment": row[2],
            }
            for row in result
        ]

    def get_columns(self, table_name: str, schema_name: str = "public") -> List[DiscoveredColumnInfo]:
        query = """
            WITH pk AS (
                SELECT kcu.column_name
                FROM information_schema.table_constraints tc
                JOIN information_schema.key_column_usage kcu
                  ON tc.constraint_name = kcu.constraint_name
                 AND tc.table_schema = kcu.table_schema
                WHERE tc.constraint_type = 'PRIMARY KEY'
                  AND tc.table_schema = :schema_name
                  AND tc.table_name = :table_name
            ),
            uq AS (
                SELECT kcu.column_name
                FROM information_schema.table_constraints tc
                JOIN information_schema.key_column_usage kcu
                  ON tc.constraint_name = kcu.constraint_name
                 AND tc.table_schema = kcu.table_schema
                WHERE tc.constraint_type = 'UNIQUE'
                  AND tc.table_schema = :schema_name
                  AND tc.table_name = :table_name
            )
            SELECT
                c.column_name,
                c.data_type,
                c.udt_name,
                c.is_nullable,
                c.column_default,
                c.character_maximum_length,
                c.numeric_precision,
                c.numeric_scale,
                CASE WHEN pk.column_name IS NOT NULL THEN true ELSE false END AS is_primary_key,
                CASE WHEN uq.column_name IS NOT NULL THEN true ELSE false END AS is_unique,
                col_description(format('%I.%I', c.table_schema, c.table_name)::regclass, c.ordinal_position) AS comment
            FROM information_schema.columns c
            LEFT JOIN pk ON c.column_name = pk.column_name
            LEFT JOIN uq ON c.column_name = uq.column_name
            WHERE c.table_schema = :schema_name
              AND c.table_name = :table_name
            ORDER BY c.ordinal_position
        """
        result = self.connection.execute_query(
            query,
            {"schema_name": schema_name, "table_name": table_name},
        )
        return [
            DiscoveredColumnInfo(
                name=row[0],
                data_type=row[1],
                udt_name=row[2],
                is_nullable=row[3] == "YES",
                column_default=row[4],
                max_length=row[5],
                numeric_precision=row[6],
                numeric_scale=row[7],
                is_primary_key=bool(row[8]),
                is_unique=bool(row[9]),
                comment=row[10],
            )
            for row in result
        ]

    def get_foreign_keys(
        self,
        table_name: Optional[str] = None,
        schema_name: str = "public",
    ) -> List[ForeignKeyInfo]:
        query = """
            SELECT
                tc.table_name,
                kcu.column_name,
                ccu.table_name AS foreign_table_name,
                ccu.column_name AS foreign_column_name
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
              ON tc.constraint_name = kcu.constraint_name
             AND tc.table_schema = kcu.table_schema
            JOIN information_schema.constraint_column_usage ccu
              ON ccu.constraint_name = tc.constraint_name
             AND ccu.table_schema = tc.table_schema
            WHERE tc.constraint_type = 'FOREIGN KEY'
              AND tc.table_schema = :schema_name
              AND (:table_name IS NULL OR tc.table_name = :table_name)
            ORDER BY tc.table_name, kcu.column_name
        """
        result = self.connection.execute_query(
            query,
            {"schema_name": schema_name, "table_name": table_name},
        )
        return [
            ForeignKeyInfo(
                table_name=row[0],
                column_name=row[1],
                foreign_table_name=row[2],
                foreign_column_name=row[3],
            )
            for row in result
        ]

    def get_indexes(self, table_name: str, schema_name: str = "public") -> List[IndexInfo]:
        query = """
            SELECT indexname, indexdef
            FROM pg_indexes
            WHERE schemaname = :schema_name
              AND tablename = :table_name
            ORDER BY indexname
        """
        result = self.connection.execute_query(
            query,
            {"schema_name": schema_name, "table_name": table_name},
        )
        return [IndexInfo(name=row[0], definition=row[1]) for row in result]

    def get_row_count(self, table_name: str, schema_name: str = "public") -> int:
        query = f"SELECT COUNT(*) FROM {self._qualified_table(schema_name, table_name)}"
        result = self.connection.execute_query(query)
        return int(result.scalar() or 0)

    def get_sample_rows(
        self,
        table_name: str,
        columns: List[DiscoveredColumnInfo],
        schema_name: str = "public",
        sample_size: int = 3,
    ) -> List[Dict[str, Any]]:
        if sample_size <= 0 or not columns:
            return []

        selected_columns = ", ".join(self._quote_identifier(column.name) for column in columns)
        query = (
            f"SELECT {selected_columns} "
            f"FROM {self._qualified_table(schema_name, table_name)} "
            "ORDER BY 1 "
            "LIMIT :sample_size"
        )
        result = self.connection.execute_query(query, {"sample_size": sample_size})
        rows = []
        for row in result.mappings():
            rows.append({key: self._json_safe(value) for key, value in row.items()})
        return rows

    def get_column_sample_values(
        self,
        table_name: str,
        column: DiscoveredColumnInfo,
        schema_name: str = "public",
        limit: int = 8,
        max_scan_rows: int = 5000,
    ) -> List[ColumnSampleValue]:
        if column.data_type not in TEXT_LIKE_TYPES and column.data_type not in {"integer", "boolean"}:
            return []
        if column.is_primary_key or column.name.endswith("_id"):
            return []

        quoted_column = self._quote_identifier(column.name)
        query = (
            f"SELECT value, COUNT(*) AS value_count FROM ("
            f"SELECT {quoted_column}::text AS value "
            f"FROM {self._qualified_table(schema_name, table_name)} "
            f"WHERE {quoted_column} IS NOT NULL "
            "LIMIT :max_scan_rows"
            ") sampled_values "
            "GROUP BY value "
            "ORDER BY value_count DESC, value ASC "
            "LIMIT :limit"
        )
        result = self.connection.execute_query(
            query,
            {"limit": limit, "max_scan_rows": max_scan_rows},
        )
        return [ColumnSampleValue(value=row[0], count=int(row[1])) for row in result]

    def build_relationships(self, foreign_keys: List[ForeignKeyInfo]) -> List[RelationshipInfo]:
        return [
            RelationshipInfo(
                source_table=fk.table_name,
                source_column=fk.column_name,
                target_table=fk.foreign_table_name,
                target_column=fk.foreign_column_name,
                relationship_type="many_to_one",
            )
            for fk in foreign_keys
        ]

    def discover(
        self,
        tenant_id: Optional[str] = None,
        schema_name: str = "public",
        sample_size: int = 3,
        sample_value_limit: int = 8,
    ) -> SchemaDiscoverySnapshot:
        tenant = tenant_id or self.settings.tenant_id
        tables = []
        all_foreign_keys = self.get_foreign_keys(schema_name=schema_name)
        foreign_keys_by_table: Dict[str, List[ForeignKeyInfo]] = {}
        for foreign_key in all_foreign_keys:
            foreign_keys_by_table.setdefault(foreign_key.table_name, []).append(foreign_key)

        for table in self.get_tables(schema_name=schema_name):
            table_name = table["name"]
            columns = self.get_columns(table_name, schema_name=schema_name)
            for column in columns:
                column.sample_values = self.get_column_sample_values(
                    table_name,
                    column,
                    schema_name=schema_name,
                    limit=sample_value_limit,
                )

            discovered_table = DiscoveredTableInfo(
                schema_name=table["schema_name"],
                name=table_name,
                comment=table["comment"],
                row_count=self.get_row_count(table_name, schema_name=schema_name),
                columns=columns,
                primary_keys=[column.name for column in columns if column.is_primary_key],
                foreign_keys=foreign_keys_by_table.get(table_name, []),
                indexes=self.get_indexes(table_name, schema_name=schema_name),
                sample_rows=self.get_sample_rows(
                    table_name,
                    columns,
                    schema_name=schema_name,
                    sample_size=sample_size,
                ),
            )
            tables.append(discovered_table)

        snapshot = SchemaDiscoverySnapshot(
            tenant_id=tenant,
            database_name=self.settings.database_name,
            schema_name=schema_name,
            generated_at=datetime.now().isoformat(timespec="seconds"),
            fingerprint="",
            tables=tables,
            relationships=self.build_relationships(all_foreign_keys),
        )
        snapshot.fingerprint = self.calculate_fingerprint(snapshot)
        return snapshot

    def calculate_fingerprint(self, snapshot: SchemaDiscoverySnapshot) -> str:
        payload = snapshot.model_dump()
        payload["generated_at"] = ""
        payload["fingerprint"] = ""
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    def save_snapshot(
        self,
        snapshot: SchemaDiscoverySnapshot,
        output_path: Optional[Path] = None,
    ) -> Path:
        path = output_path or self._tenant_dir(snapshot.tenant_id) / "discovery.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as file:
            json.dump(snapshot.model_dump(), file, ensure_ascii=False, indent=2, default=str)
        return path

    def sync_discovery(
        self,
        tenant_id: Optional[str] = None,
        schema_name: str = "public",
        sample_size: int = 3,
        sample_value_limit: int = 8,
        output_path: Optional[Path] = None,
    ) -> SchemaDiscoveryResponse:
        try:
            snapshot = self.discover(
                tenant_id=tenant_id,
                schema_name=schema_name,
                sample_size=sample_size,
                sample_value_limit=sample_value_limit,
            )
            saved_path = self.save_snapshot(snapshot, output_path)
            return SchemaDiscoveryResponse(
                tenant_id=snapshot.tenant_id,
                tables_discovered=len(snapshot.tables),
                relationships_found=len(snapshot.relationships),
                fingerprint=snapshot.fingerprint,
                output_path=str(saved_path),
                status="success",
            )
        except Exception as exc:
            return SchemaDiscoveryResponse(
                tenant_id=tenant_id or self.settings.tenant_id,
                tables_discovered=0,
                relationships_found=0,
                fingerprint="",
                output_path=str(output_path) if output_path else None,
                status=f"error: {exc}",
            )


schema_discovery_service = SchemaDiscoveryService()
