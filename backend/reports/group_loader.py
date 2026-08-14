import yaml
from pathlib import Path
from typing import List, Optional
from backend.reports.group_models import ReportGroup


class GroupLoader:
    def __init__(self, tenant_path: Path):
        self.groups_path = tenant_path / "groups"
    
    def load_group(self, group_id: str) -> Optional[ReportGroup]:
        group_file = self.groups_path / f"{group_id}.yaml"
        if not group_file.exists():
            return None
        
        with open(group_file, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)
        
        if data:
            return ReportGroup(**data)
        return None
    
    def load_all_groups(self) -> List[ReportGroup]:
        if not self.groups_path.exists():
            return []
        
        groups = []
        for group_file in self.groups_path.glob("*.yaml"):
            with open(group_file, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)
            if data:
                groups.append(ReportGroup(**data))
        
        return groups


group_loader = GroupLoader
