from pydantic import BaseModel
from typing import List, Optional, Dict, Any


class ColumnInfo(BaseModel):
    name: str
    data_type: str
    is_nullable: bool = True
    column_default: Optional[str] = None
    is_primary_key: bool = False


class TableInfo(BaseModel):
    name: str
    columns: List[ColumnInfo] = []
    primary_keys: List[str] = []
    row_count: Optional[int] = None


class ForeignKeyInfo(BaseModel):
    table_name: str
    column_name: str
    foreign_table_name: str
    foreign_column_name: str


class RelationshipInfo(BaseModel):
    source_table: str
    source_column: str
    target_table: str
    target_column: str
    relationship_type: str = "many_to_one"


class DatabaseSchema(BaseModel):
    tables: List[TableInfo] = []
    foreign_keys: List[ForeignKeyInfo] = []
    relationships: List[RelationshipInfo] = []


class SchemaSyncResponse(BaseModel):
    tenant_id: str
    tables_discovered: int
    relationships_found: int
    status: str


class ColumnSampleValue(BaseModel):
    value: Optional[str] = None
    count: int = 0


class DiscoveredColumnInfo(BaseModel):
    name: str
    data_type: str
    udt_name: str
    is_nullable: bool = True
    column_default: Optional[str] = None
    max_length: Optional[int] = None
    numeric_precision: Optional[int] = None
    numeric_scale: Optional[int] = None
    is_primary_key: bool = False
    is_unique: bool = False
    comment: Optional[str] = None
    sample_values: List[ColumnSampleValue] = []


class IndexInfo(BaseModel):
    name: str
    definition: str


class DiscoveredTableInfo(BaseModel):
    schema_name: str = "public"
    name: str
    comment: Optional[str] = None
    row_count: int = 0
    columns: List[DiscoveredColumnInfo] = []
    primary_keys: List[str] = []
    foreign_keys: List[ForeignKeyInfo] = []
    indexes: List[IndexInfo] = []
    sample_rows: List[Dict[str, Any]] = []


class SchemaDiscoverySnapshot(BaseModel):
    tenant_id: str
    database_name: str
    schema_name: str = "public"
    generated_at: str
    fingerprint: str
    tables: List[DiscoveredTableInfo] = []
    relationships: List[RelationshipInfo] = []


class SchemaDiscoveryResponse(BaseModel):
    tenant_id: str
    tables_discovered: int
    relationships_found: int
    inferred_relationships: int = 0
    fingerprint: str
    output_path: Optional[str] = None
    status: str
