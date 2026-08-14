import json
from pathlib import Path
from backend.config import get_settings
from backend.database.schema_loader import schema_loader
from backend.database.relationship_graph import relationship_graph
from backend.database.models import DatabaseSchema, SchemaSyncResponse


class SchemaSyncService:
    def __init__(self):
        self.settings = get_settings()
        self.schema_dir = Path(__file__).parent.parent.parent / "schema" / "tenants"
    
    def _get_tenant_schema_dir(self, tenant_id: str) -> Path:
        tenant_dir = self.schema_dir / tenant_id
        tenant_dir.mkdir(parents=True, exist_ok=True)
        return tenant_dir
    
    def sync_schema(self, tenant_id: str) -> SchemaSyncResponse:
        try:
            schema = schema_loader.load_full_schema()
            
            relationships = relationship_graph.build_from_foreign_keys(schema.foreign_keys)
            schema.relationships = relationships
            
            tenant_dir = self._get_tenant_schema_dir(tenant_id)
            
            tables_data = [table.model_dump() for table in schema.tables]
            with open(tenant_dir / "tables.json", "w", encoding="utf-8") as f:
                json.dump(tables_data, f, ensure_ascii=False, indent=2)
            
            relationships_data = [rel.model_dump() for rel in relationships]
            with open(tenant_dir / "relationships.json", "w", encoding="utf-8") as f:
                json.dump(relationships_data, f, ensure_ascii=False, indent=2)
            
            return SchemaSyncResponse(
                tenant_id=tenant_id,
                tables_discovered=len(schema.tables),
                relationships_found=len(relationships),
                status="success"
            )
        except Exception as e:
            return SchemaSyncResponse(
                tenant_id=tenant_id,
                tables_discovered=0,
                relationships_found=0,
                status=f"error: {str(e)}"
            )
    
    def load_schema(self, tenant_id: str) -> DatabaseSchema:
        tenant_dir = self._get_tenant_schema_dir(tenant_id)
        
        tables_file = tenant_dir / "tables.json"
        relationships_file = tenant_dir / "relationships.json"
        
        tables = []
        if tables_file.exists():
            with open(tables_file, "r", encoding="utf-8") as f:
                tables_data = json.load(f)
                from backend.database.models import TableInfo, ColumnInfo
                for table_data in tables_data:
                    columns = [ColumnInfo(**col) for col in table_data.get("columns", [])]
                    tables.append(TableInfo(
                        name=table_data["name"],
                        columns=columns,
                        primary_keys=table_data.get("primary_keys", []),
                        row_count=table_data.get("row_count")
                    ))
        
        relationships = []
        if relationships_file.exists():
            with open(relationships_file, "r", encoding="utf-8") as f:
                rels_data = json.load(f)
                from backend.database.models import RelationshipInfo
                relationships = [RelationshipInfo(**rel) for rel in rels_data]
        
        from backend.database.models import ForeignKeyInfo
        foreign_keys = []
        for rel in relationships:
            foreign_keys.append(ForeignKeyInfo(
                table_name=rel.source_table,
                column_name=rel.source_column,
                foreign_table_name=rel.target_table,
                foreign_column_name=rel.target_column
            ))
        
        return DatabaseSchema(
            tables=tables,
            foreign_keys=foreign_keys,
            relationships=relationships
        )


schema_sync_service = SchemaSyncService()
