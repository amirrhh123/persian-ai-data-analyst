import chromadb
from typing import List, Dict, Any, Optional
from backend.config import get_settings


class VectorStore:
    def __init__(self):
        self.settings = get_settings()
        self.client = None
        self._collections: Dict[str, Any] = {}
    
    def _get_client(self):
        if self.client is None:
            self.client = chromadb.HttpClient(
                host=self.settings.chroma_host,
                port=self.settings.chroma_port
            )
        return self.client
    
    def _get_collection_name(self, tenant_id: str) -> str:
        return f"reports_{tenant_id}"
    
    def get_collection(self, tenant_id: str):
        collection_name = self._get_collection_name(tenant_id)
        
        if collection_name not in self._collections:
            client = self._get_client()
            self._collections[collection_name] = client.get_or_create_collection(
                name=collection_name,
                metadata={"hnsw:space": "cosine"}
            )
        
        return self._collections[collection_name]
    
    def add_documents(
        self,
        tenant_id: str,
        ids: List[str],
        documents: List[str],
        metadatas: List[Dict[str, Any]],
        embeddings: Optional[List[List[float]]] = None
    ):
        collection = self.get_collection(tenant_id)
        
        if embeddings:
            collection.add(
                ids=ids,
                documents=documents,
                metadatas=metadatas,
                embeddings=embeddings
            )
        else:
            collection.add(
                ids=ids,
                documents=documents,
                metadatas=metadatas
            )
    
    def query(
        self,
        tenant_id: str,
        query_embedding: Optional[List[float]] = None,
        n_results: int = 3
    ) -> Dict[str, Any]:
        collection = self.get_collection(tenant_id)
        
        if query_embedding:
            results = collection.query(
                query_embeddings=[query_embedding],
                n_results=n_results
            )
        else:
            return {"ids": [], "documents": [], "metadatas": [], "distances": []}
        
        return results
    
    def delete_collection(self, tenant_id: str):
        collection_name = self._get_collection_name(tenant_id)
        client = self._get_client()
        
        try:
            client.delete_collection(collection_name)
            if collection_name in self._collections:
                del self._collections[collection_name]
        except Exception:
            pass
    
    def get_collection_count(self, tenant_id: str) -> int:
        collection = self.get_collection(tenant_id)
        return collection.count()


vector_store = VectorStore()
