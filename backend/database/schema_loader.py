from sqlalchemy import text
from typing import List, Dict, Any
from backend.database.connection import db_connection
from backend.database.models import TableInfo, ColumnInfo, ForeignKeyInfo, DatabaseSchema


class SchemaLoader:
    def __init__(self):
        self.connection = db_connection
    
    def get_tables(self) -> List[str]:
        query = """
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_type = 'BASE TABLE'
            ORDER BY table_name
        """
        result = self.connection.execute_query(query)
        return [row[0] for row in result]
    
    def get_columns(self, table_name: str) -> List[ColumnInfo]:
        query = """
            SELECT 
                c.column_name,
                c.data_type,
                c.is_nullable,
                c.column_default,
                CASE WHEN pk.column_name IS NOT NULL THEN true ELSE false END as is_primary_key
            FROM information_schema.columns c
            LEFT JOIN (
                SELECT ku.column_name
                FROM information_schema.table_constraints tc
                JOIN information_schema.key_column_usage ku
                    ON tc.constraint_name = ku.constraint_name
                    AND tc.table_schema = ku.table_schema
                WHERE tc.constraint_type = 'PRIMARY KEY'
                AND tc.table_name = :table_name
            ) pk ON c.column_name = pk.column_name
            WHERE c.table_name = :table_name
            AND c.table_schema = 'public'
            ORDER BY c.ordinal_position
        """
        result = self.connection.execute_query(query, {"table_name": table_name})
        columns = []
        for row in result:
            columns.append(ColumnInfo(
                name=row[0],
                data_type=row[1],
                is_nullable=row[2] == 'YES',
                column_default=row[3],
                is_primary_key=row[4]
            ))
        return columns
    
    def get_primary_keys(self, table_name: str) -> List[str]:
        query = """
            SELECT ku.column_name
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage ku
                ON tc.constraint_name = ku.constraint_name
                AND tc.table_schema = ku.table_schema
            WHERE tc.constraint_type = 'PRIMARY KEY'
            AND tc.table_name = :table_name
            AND tc.table_schema = 'public'
        """
        result = self.connection.execute_query(query, {"table_name": table_name})
        return [row[0] for row in result]
    
    def get_foreign_keys(self) -> List[ForeignKeyInfo]:
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
            AND tc.table_schema = 'public'
        """
        result = self.connection.execute_query(query)
        foreign_keys = []
        for row in result:
            foreign_keys.append(ForeignKeyInfo(
                table_name=row[0],
                column_name=row[1],
                foreign_table_name=row[2],
                foreign_column_name=row[3]
            ))
        return foreign_keys
    
    def get_table_row_count(self, table_name: str) -> int:
        query = f"SELECT COUNT(*) FROM {table_name}"
        result = self.connection.execute_query(query)
        return result.scalar()
    
    def load_full_schema(self) -> DatabaseSchema:
        tables = []
        all_foreign_keys = self.get_foreign_keys()
        
        for table_name in self.get_tables():
            columns = self.get_columns(table_name)
            primary_keys = self.get_primary_keys(table_name)
            row_count = self.get_table_row_count(table_name)
            
            tables.append(TableInfo(
                name=table_name,
                columns=columns,
                primary_keys=primary_keys,
                row_count=row_count
            ))
        
        return DatabaseSchema(
            tables=tables,
            foreign_keys=all_foreign_keys
        )


schema_loader = SchemaLoader()
