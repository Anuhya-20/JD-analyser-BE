from typing import List
from functools import lru_cache
from loguru import logger
from app.config import settings


class EmbeddingService:
    """
    Singleton service for generating text embeddings using BAAI/bge-base-en-v1.5.
    Produces 768-dimensional vectors.
    """

    _model = None

    def _load_model(self):
        if self._model is None:
            logger.info(f"Loading embedding model: {settings.EMBEDDING_MODEL}")
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(
                settings.EMBEDDING_MODEL,
                device=settings.EMBEDDING_DEVICE,
            )
            logger.info("Embedding model loaded successfully")

    def embed_text(self, text: str) -> List[float]:
        """Generate embedding for a single text string."""
        self._load_model()
        # BGE models recommend prepending a query instruction
        text = f"Represent this sentence for searching relevant passages: {text}"
        embedding = self._model.encode(text, normalize_embeddings=True)
        return embedding.tolist()

    def embed_texts(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for multiple texts in a batch."""
        self._load_model()
        prefixed = [
            f"Represent this sentence for searching relevant passages: {t}"
            for t in texts
        ]
        embeddings = self._model.encode(
            prefixed,
            normalize_embeddings=True,
            batch_size=32,
            show_progress_bar=False,
        )
        return [emb.tolist() for emb in embeddings]

    def embed_document(self, text: str) -> List[float]:
        """Generate embedding for a document (no query prefix)."""
        self._load_model()
        embedding = self._model.encode(text, normalize_embeddings=True)
        return embedding.tolist()

    def cosine_similarity(self, vec1: List[float], vec2: List[float]) -> float:
        """Compute cosine similarity between two embedding vectors."""
        import numpy as np
        v1 = np.array(vec1)
        v2 = np.array(vec2)
        norm1 = np.linalg.norm(v1)
        norm2 = np.linalg.norm(v2)
        if norm1 == 0 or norm2 == 0:
            return 0.0
        return float(np.dot(v1, v2) / (norm1 * norm2))


embedding_service = EmbeddingService()
