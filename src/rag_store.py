"""
RAG vector store backed by Milvus Lite.

Stores competitive product knowledge as vector embeddings for fast,
semantic retrieval during expert-agent verification and future agent queries.
"""

import os
import uuid
from dataclasses import dataclass
from typing import Any, Optional

# Workaround for multiple OpenMP runtimes loaded by Milvus Lite + sentence-transformers
os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

from pymilvus import DataType, FieldSchema, CollectionSchema, MilvusClient

try:
    from pymilvus import IndexParams
except ImportError:
    IndexParams = None

from .embeddings import EmbeddingModelCache


@dataclass
class RetrievedChunk:
    """A single chunk retrieved from the RAG store."""

    doc_id: str
    file_name: str
    chunk_text: str
    distance: float
    metadata: dict[str, Any]


class RAGStore:
    """
    Vector store for competitive intelligence documents and facts.

    Uses Milvus Lite (local file) by default. Pass a custom uri to use
    a standalone Milvus server.
    """

    _COLLECTION_NAME = "competitive_kb"

    def __init__(
        self,
        uri: str = "output/milvus_kb.db",
        collection_name: Optional[str] = None,
    ):
        self.uri = uri
        self.collection_name = collection_name or self._COLLECTION_NAME
        os.makedirs(os.path.dirname(uri) or ".", exist_ok=True)
        self.client = MilvusClient(uri=uri)
        self._ensure_collection()

    def _ensure_collection(self) -> None:
        if self.client.has_collection(self.collection_name):
            return

        schema = CollectionSchema(
            fields=[
                FieldSchema(name="id", dtype=DataType.VARCHAR, max_length=64, is_primary=True),
                FieldSchema(name="doc_id", dtype=DataType.VARCHAR, max_length=64),
                FieldSchema(name="file_name", dtype=DataType.VARCHAR, max_length=512),
                FieldSchema(name="chunk_text", dtype=DataType.VARCHAR, max_length=8192),
                FieldSchema(name="chunk_type", dtype=DataType.VARCHAR, max_length=32),
                FieldSchema(name="product_name", dtype=DataType.VARCHAR, max_length=256),
                FieldSchema(name="dimension_name", dtype=DataType.VARCHAR, max_length=256),
                FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=EmbeddingModelCache().get_dimension()),
            ],
            description="Competitive product knowledge base vectors",
        )
        self.client.create_collection(
            collection_name=self.collection_name,
            schema=schema,
        )
        if IndexParams is not None:
            index_params = IndexParams()
            index_params.add_index(
                field_name="embedding",
                metric_type="COSINE",
                index_type="FLAT",
            )
        else:
            index_params = self.client.prepare_index_params()
            index_params.add_index(
                field_name="embedding",
                metric_type="COSINE",
                index_type="FLAT",
            )
        self.client.create_index(
            collection_name=self.collection_name,
            index_params=index_params,
        )
        self.client.load_collection(self.collection_name)

    def _embed(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings using the shared cached model."""
        return EmbeddingModelCache().encode(texts)

    def add_document_chunks(
        self,
        doc_id: str,
        file_name: str,
        chunks: list[str],
        product_name: str = "",
        dimension_name: str = "",
    ) -> None:
        """Add raw document chunks to the vector store."""
        chunks = [c.strip() for c in chunks if c.strip()]
        if not chunks:
            return

        embeddings = self._embed(chunks)
        rows = [
            {
                "id": f"{doc_id}_chunk_{i}_{uuid.uuid4().hex[:6]}",
                "doc_id": doc_id,
                "file_name": file_name,
                "chunk_text": chunk[:8192],
                "chunk_type": "document",
                "product_name": product_name,
                "dimension_name": dimension_name,
                "embedding": emb,
            }
            for i, (chunk, emb) in enumerate(zip(chunks, embeddings))
        ]
        self.client.insert(self.collection_name, rows)

    def add_fact(
        self,
        fact_content: str,
        doc_id: str,
        file_name: str,
        product_name: str = "",
        dimension_name: str = "",
    ) -> None:
        """Add a single fact item to the vector store."""
        if not fact_content or not fact_content.strip():
            return
        embedding = self._embed([fact_content])[0]
        self.client.insert(
            self.collection_name,
            [
                {
                    "id": f"fact_{uuid.uuid4().hex[:8]}",
                    "doc_id": doc_id,
                    "file_name": file_name,
                    "chunk_text": fact_content[:8192],
                    "chunk_type": "fact",
                    "product_name": product_name,
                    "dimension_name": dimension_name,
                    "embedding": embedding,
                }
            ],
        )

    def retrieve(
        self,
        query: str,
        top_k: int = 3,
        product_name: Optional[str] = None,
    ) -> list[RetrievedChunk]:
        """Retrieve the most relevant chunks for a query."""
        if not query or not query.strip():
            return []
        self.client.load_collection(self.collection_name)
        embedding = self._embed([query])[0]

        filters = None
        if product_name:
            filters = f'product_name == "{product_name}"'

        results = self.client.search(
            collection_name=self.collection_name,
            data=[embedding],
            filter=filters,
            limit=top_k,
            output_fields=["doc_id", "file_name", "chunk_text", "chunk_type", "product_name", "dimension_name"],
            search_params={"metric_type": "COSINE", "params": {}},
        )

        chunks: list[RetrievedChunk] = []
        for result in results[0]:
            entity = result["entity"]
            chunks.append(
                RetrievedChunk(
                    doc_id=entity["doc_id"],
                    file_name=entity["file_name"],
                    chunk_text=entity["chunk_text"],
                    distance=result["distance"],
                    metadata={
                        "chunk_type": entity["chunk_type"],
                        "product_name": entity.get("product_name", ""),
                        "dimension_name": entity.get("dimension_name", ""),
                    },
                )
            )
        return chunks

    def clear(self) -> None:
        """Drop all data in the collection."""
        if self.client.has_collection(self.collection_name):
            self.client.drop_collection(self.collection_name)
        self._ensure_collection()
