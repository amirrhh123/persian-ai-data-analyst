from typing import List, Dict
from backend.database.models import ForeignKeyInfo, RelationshipInfo


class RelationshipGraph:
    def __init__(self):
        self.relationships: List[RelationshipInfo] = []
        self.graph: Dict[str, List[Dict]] = {}
    
    def build_from_foreign_keys(self, foreign_keys: List[ForeignKeyInfo]) -> List[RelationshipInfo]:
        self.relationships = []
        self.graph = {}
        
        for fk in foreign_keys:
            relationship = RelationshipInfo(
                source_table=fk.table_name,
                source_column=fk.column_name,
                target_table=fk.foreign_table_name,
                target_column=fk.foreign_column_name,
                relationship_type="many_to_one"
            )
            self.relationships.append(relationship)
            
            if fk.table_name not in self.graph:
                self.graph[fk.table_name] = []
            self.graph[fk.table_name].append({
                "column": fk.column_name,
                "references_table": fk.foreign_table_name,
                "references_column": fk.foreign_column_name
            })
            
            if fk.foreign_table_name not in self.graph:
                self.graph[fk.foreign_table_name] = []
            self.graph[fk.foreign_table_name].append({
                "column": fk.foreign_column_name,
                "referenced_by_table": fk.table_name,
                "referenced_by_column": fk.column_name,
                "is_reverse": True
            })
        
        return self.relationships
    
    def get_relationships_for_table(self, table_name: str) -> List[Dict]:
        return self.graph.get(table_name, [])
    
    def find_join_path(self, table1: str, table2: str) -> List[Dict]:
        if table1 == table2:
            return []
        
        if table1 in self.graph:
            for rel in self.graph[table1]:
                if rel.get("references_table") == table2:
                    return [{
                        "from_table": table1,
                        "from_column": rel["column"],
                        "to_table": table2,
                        "to_column": rel["references_column"]
                    }]
        
        if table2 in self.graph:
            for rel in self.graph[table2]:
                if rel.get("references_table") == table1:
                    return [{
                        "from_table": table2,
                        "from_column": rel["column"],
                        "to_table": table1,
                        "to_column": rel["references_column"]
                    }]
        
        return []
    
    def get_all_relationships(self) -> List[RelationshipInfo]:
        return self.relationships


relationship_graph = RelationshipGraph()
