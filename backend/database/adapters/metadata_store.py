import json
from pathlib import Path
from typing import Dict, Any, Optional
from backend.config import get_settings


class MetadataStore:
    def __init__(self):
        self.settings = get_settings()
        self.base_dir = Path(__file__).parent.parent.parent.parent / "schema" / "tenants"
    
    def _get_tenant_dir(self, tenant_id: str) -> Path:
        tenant_dir = self.base_dir / tenant_id
        tenant_dir.mkdir(parents=True, exist_ok=True)
        return tenant_dir
    
    def save_tables(self, tenant_id: str, tables: List[Dict]) -> None:
        tenant_dir = self._get_tenant_dir(tenant_id)
        with open(tenant_dir / "tables.json", "w", encoding="utf-8") as f:
            json.dump(tables, f, ensure_ascii=False, indent=2)
    
    def load_tables(self, tenant_id: str) -> List[Dict]:
        tenant_dir = self._get_tenant_dir(tenant_id)
        tables_file = tenant_dir / "tables.json"
        if tables_file.exists():
            with open(tables_file, "r", encoding="utf-8") as f:
                return json.load(f)
        return []
    
    def save_relationships(self, tenant_id: str, relationships: List[Dict]) -> None:
        tenant_dir = self._get_tenant_dir(tenant_id)
        with open(tenant_dir / "relationships.json", "w", encoding="utf-8") as f:
            json.dump(relationships, f, ensure_ascii=False, indent=2)
    
    def load_relationships(self, tenant_id: str) -> List[Dict]:
        tenant_dir = self._get_tenant_dir(tenant_id)
        rels_file = tenant_dir / "relationships.json"
        if rels_file.exists():
            with open(rels_file, "r", encoding="utf-8") as f:
                return json.load(f)
        return []
    
    def save_sync_info(self, tenant_id: str, info: Dict) -> None:
        tenant_dir = self._get_tenant_dir(tenant_id)
        with open(tenant_dir / "sync_info.json", "w", encoding="utf-8") as f:
            json.dump(info, f, ensure_ascii=False, indent=2)
    
    def load_sync_info(self, tenant_id: str) -> Dict:
        tenant_dir = self._get_tenant_dir(tenant_id)
        info_file = tenant_dir / "sync_info.json"
        if info_file.exists():
            with open(info_file, "r", encoding="utf-8") as f:
                return json.load(f)
        return {}
    
    def get_last_sync(self, tenant_id: str) -> Optional[str]:
        info = self.load_sync_info(tenant_id)
        return info.get("last_sync")
    
    def update_sync(self, tenant_id: str, table_count: int, relationship_count: int) -> None:
        from datetime import datetime
        info = {
            "last_sync": datetime.now().isoformat(),
            "tables_count": table_count,
            "relationships_count": relationship_count
        }
        self.save_sync_info(tenant_id, info)


from typing import List


metadata_store = MetadataStore()
