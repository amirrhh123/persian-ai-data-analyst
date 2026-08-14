from typing import List, Dict, Any
from pathlib import Path
from backend.reports.group_models import ReportGroup, EntityTerm
from backend.reports.group_loader import GroupLoader
from backend.reports.embedding import embedding_service
from backend.reports.hybrid_retrieval import HybridCandidate, hybrid_retriever
from backend.reports.vector_store import vector_store


class GroupRetriever:
    def __init__(self):
        self.tenants_dir = Path(__file__).parent.parent.parent / "knowledge" / "tenants"
    
    def _prepare_document(self, group: ReportGroup) -> str:
        parts = [
            f"نام گروه: {group.name}",
            f"توضیحات: {group.description}",
        ]
        
        if group.keywords:
            parts.append(f"کلمات کلیدی: {', '.join(group.keywords)}")
        
        if group.linked_tables:
            parts.append(f"جداول مرتبط: {', '.join(group.linked_tables)}")
        
        if group.domain_terms:
            parts.append(f"اصطلاحات تخصصی: {', '.join(group.domain_terms)}")
        
        if group.example_questions:
            parts.append(f"نمونه سوالات: {', '.join(group.example_questions)}")
        
        return "\n".join(parts)
    
    def _prepare_metadata(self, group: ReportGroup, tenant_id: str) -> Dict[str, Any]:
        return {
            "group_id": group.id,
            "tenant_id": tenant_id,
            "group_name": group.name,
            "linked_tables": ",".join(group.linked_tables)
        }
    
    def _keyword_boost(self, question: str, group: ReportGroup) -> float:
        boost = 0.0
        q = question.lower()
        
        if group.priority_terms:
            for term in group.priority_terms:
                if term.lower() in q:
                    boost += 0.15
        
        if group.excluded_topics:
            for term in group.excluded_topics:
                if term.lower() in q:
                    boost -= 0.20
        
        return boost
    
    def _entity_boost(self, question: str, group: ReportGroup) -> float:
        boost = 0.0
        q = question.lower()
        
        for entity in group.entity_terms:
            if entity.term.lower() in q:
                boost += entity.weight * 0.1
        
        return boost
    
    def sync_groups(self, tenant_id: str) -> int:
        tenant_path = self.tenants_dir / tenant_id
        loader = GroupLoader(tenant_path)
        
        groups = loader.load_all_groups()
        
        if not groups:
            return 0
        
        ids = []
        documents = []
        metadatas = []
        
        for group in groups:
            document = self._prepare_document(group)
            metadata = self._prepare_metadata(group, tenant_id)
            
            ids.append(f"{tenant_id}_group_{group.id}")
            documents.append(document)
            metadatas.append(metadata)
        
        embeddings = embedding_service.embed_batch(documents)
        
        collection_name = f"groups_{tenant_id}"
        
        client = vector_store._get_client()
        
        try:
            client.delete_collection(collection_name)
        except Exception:
            pass
        
        collection = client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"}
        )
        
        collection.add(
            ids=ids,
            documents=documents,
            metadatas=metadatas,
            embeddings=embeddings
        )
        
        return len(groups)
    
    def search_groups(
        self,
        tenant_id: str,
        question: str,
        n_results: int = 3,
    ) -> Dict[str, Any]:
        """Find the best report group using dense and lexical evidence."""
        collection_name = f"groups_{tenant_id}"
        try:
            client = vector_store._get_client()
            collection = client.get_collection(collection_name)
        except Exception:
            return self._empty_result()

        loader = GroupLoader(self.tenants_dir / tenant_id)
        groups = loader.load_all_groups()
        if not groups:
            return self._empty_result()

        query_embedding = embedding_service.embed_text(question)
        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=len(groups),
        )
        vector_scores: Dict[str, float] = {}
        metadatas = (results.get("metadatas") or [[]])[0]
        distances = (results.get("distances") or [[]])[0]
        for index, metadata in enumerate(metadatas):
            group_id = metadata.get("group_id", "")
            distance = distances[index] if index < len(distances) else 1.0
            vector_scores[group_id] = max(0.0, min(1.0, 1.0 - distance))

        for group in groups:
            score = vector_scores.get(group.id, 0.0)
            score += self._keyword_boost(question, group)
            score += self._entity_boost(question, group)
            vector_scores[group.id] = max(0.0, min(1.0, score))

        candidates = [
            HybridCandidate(
                id=group.id,
                document=self._prepare_document(group),
                metadata=self._prepare_metadata(group, tenant_id),
            )
            for group in groups
        ]
        ranked = hybrid_retriever.rank(question, candidates, vector_scores)
        if not ranked:
            return self._empty_result()

        best = ranked[0]
        group_name = str(best.candidate.metadata.get("group_name", ""))
        return {
            "group_id": best.candidate.id,
            "group_name": group_name,
            "confidence": round(best.final_score, 2),
            "reason": (
                f"گروه '{group_name}' با بازیابی ترکیبی و اطمینان "
                f"{best.final_score:.2f} یافت شد"
            ),
            "retrieval_mode": "hybrid",
            "vector_score": best.vector_score,
            "lexical_score": best.lexical_score,
            "top_candidates": [
                {
                    "group_id": item.candidate.id,
                    "group_name": item.candidate.metadata.get("group_name", ""),
                    "vector_score": item.vector_score,
                    "lexical_score": item.lexical_score,
                    "final_score": item.final_score,
                }
                for item in ranked[:n_results]
            ],
        }

    @staticmethod
    def _empty_result() -> Dict[str, Any]:
        """Return a stable response when no group can be retrieved."""
        return {
            "group_id": "",
            "group_name": "",
            "confidence": 0.0,
            "reason": "هیچ گروهی یافت نشد",
            "retrieval_mode": "hybrid",
            "vector_score": 0.0,
            "lexical_score": 0.0,
            "top_candidates": [],
        }

    def _search_groups_vector(
        self,
        tenant_id: str,
        question: str,
        n_results: int = 3
    ) -> Dict[str, Any]:
        query_embedding = embedding_service.embed_text(question)
        
        collection_name = f"groups_{tenant_id}"
        client = vector_store._get_client()
        
        try:
            collection = client.get_collection(collection_name)
        except Exception:
            return {
                "group_id": "",
                "group_name": "",
                "confidence": 0.0,
                "reason": "هیچ گروهی یافت نشد"
            }
        
        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=n_results
        )
        
        if not results["ids"] or not results["ids"][0]:
            return {
                "group_id": "",
                "group_name": "",
                "confidence": 0.0,
                "reason": "هیچ گروهی یافت نشد"
            }
        
        tenant_path = self.tenants_dir / tenant_id
        loader = GroupLoader(tenant_path)
        all_groups = {g.id: g for g in loader.load_all_groups()}
        
        best_id = ""
        best_name = ""
        best_score = -999.0
        best_distance = 1.0
        
        for i in range(len(results["ids"][0])):
            gid = results["metadatas"][0][i].get("group_id", "")
            gname = results["metadatas"][0][i].get("group_name", "")
            distance = results["distances"][0][i] if results["distances"] else 1.0
            
            vector_score = 1.0 - distance
            
            keyword_boost = 0.0
            entity_boost = 0.0
            if gid in all_groups:
                keyword_boost = self._keyword_boost(question, all_groups[gid])
                entity_boost = self._entity_boost(question, all_groups[gid])
            
            final_score = vector_score + keyword_boost + entity_boost
            
            if final_score > best_score:
                best_score = final_score
                best_id = gid
                best_name = gname
                best_distance = distance
        
        confidence = max(0.0, min(1.0, best_score))
        reason = f"گروه '{best_name}' با اطمینان {confidence:.2f} یافت شد"
        
        return {
            "group_id": best_id,
            "group_name": best_name,
            "confidence": round(confidence, 2),
            "reason": reason
        }


group_retriever = GroupRetriever()
