from sentence_transformers import SentenceTransformer
from backend.config import get_settings
from typing import List


class EmbeddingService:
    def __init__(self):
        self.settings = get_settings()
        self.model = None
    
    def _load_model(self):
        if self.model is None:
            try:
                self.model = SentenceTransformer(
                    self.settings.embedding_model_path,
                    device=self.settings.embedding_device
                )
            except Exception as e:
                raise RuntimeError(
                    f"Failed to load embedding model '{self.settings.embedding_model_path}'. "
                    f"Ensure the model is downloaded locally. Error: {str(e)}"
                )
        return self.model
    
    def embed_text(self, text: str) -> List[float]:
        model = self._load_model()
        embedding = model.encode(text)
        return embedding.tolist()
    
    def embed_batch(self, texts: List[str]) -> List[List[float]]:
        model = self._load_model()
        embeddings = model.encode(texts)
        return embeddings.tolist()
    
    def get_dimension(self) -> int:
        model = self._load_model()
        return model.get_sentence_embedding_dimension()


embedding_service = EmbeddingService()
