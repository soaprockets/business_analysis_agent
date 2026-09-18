"""
Shared embedding model cache to avoid reloading the sentence-transformers model
multiple times within the same process.
"""

import math
import os
from typing import Any


class EmbeddingModelCache:
    """Singleton cache for the embedding model."""

    _instance: "EmbeddingModelCache | None" = None
    _model: Any | None = None
    _model_name: str = os.getenv("EMBEDDING_MODEL_NAME", "BAAI/bge-small-zh-v1.5")

    def __new__(cls) -> "EmbeddingModelCache":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def get_model(self, model_name: str | None = None) -> Any:
        """Load and cache the embedding model."""
        name = model_name or self._model_name
        if self._model is None or name != self._model_name:
            from sentence_transformers import SentenceTransformer

            self._model_name = name
            self._model = SentenceTransformer(name)
        return self._model

    def get_dimension(self) -> int:
        """Return the embedding dimension of the loaded model."""
        model = self.get_model()
        return model.get_sentence_embedding_dimension()

    def warmup(self) -> None:
        """Warm up the model so the first real encode call is fast."""
        self.encode(["warmup"])

    def encode(self, texts: list[str]) -> list[list[float]]:
        """Encode texts using the cached model."""
        # Replace empty strings to avoid degenerate embeddings
        safe_texts = [t if t.strip() else " " for t in texts]
        model = self.get_model()
        embeddings = model.encode(
            safe_texts,
            convert_to_numpy=True,
            show_progress_bar=False,
            normalize_embeddings=True,
        )

        # Sanitize embeddings: replace NaN/Inf with zeros
        result: list[list[float]] = []
        dim = embeddings.shape[1]
        for vec in embeddings:
            cleaned = []
            has_invalid = False
            for v in vec:
                if math.isnan(v) or math.isinf(v):
                    cleaned.append(0.0)
                    has_invalid = True
                else:
                    cleaned.append(float(v))
            if has_invalid or all(x == 0.0 for x in cleaned):
                cleaned = [0.0] * dim
            result.append(cleaned)
        return result
