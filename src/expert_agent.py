"""
Expert agent that reads competitive product documents and builds a structured,
dynamic knowledge base without relying on pre-defined dimensions.
"""

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from .models import (
    ConflictRecord,
    Dimension,
    FactItem,
    KnowledgeBase,
    ProductProfile,
    SearchResult,
    SourceDocument,
    SourceRef,
)
from .parser import ParsedDocument
from .utils import extract_json_block

load_dotenv()


EXTRACTION_PROMPT = """You are a "Competitive Product Expert Agent". Your job is to read the provided source documents and build a structured knowledge base about competitive products mentioned in them.

## Core Rules

1. **Base everything on the documents only.** Do not add information from your own knowledge.
2. **Do not use pre-defined dimensions.** Discover dimensions naturally from the text. For example, if the documents talk about "pricing", "target users", "AI features", "security certifications", then those become dimensions.
3. **Each product gets its own profile.** Identify every distinct competitive product mentioned.
4. **Each fact must have a source reference.** Use `doc_id` and `file_name` from the document list below. Include a page number or section heading when available. Include a short quote when helpful.
5. **Summarize facts in your own words**, but keep them grounded in the document. Do not copy long passages.
6. **Use status values correctly:**
   - `confirmed`: the fact is clearly stated in the documents.
   - `pending_verification`: the fact is mentioned but unclear or incomplete.
   - `not_mentioned`: the dimension is being noted as absent from the documents (do not invent facts for it).
   - `conflict`: the documents contradict each other.
7. **Confidence levels:** `high`, `medium`, or `low`.
8. If a product is only mentioned briefly without useful details, still create a profile with a summary and minimal dimensions.

## Output Format

Return a single JSON object matching this structure exactly:

```json
{
  "products": [
    {
      "product_id": "p_001",
      "product_name": "Product Name",
      "company_name": "Company Name (if known)",
      "summary": {
        "item_id": "i_001",
        "content": "One or two sentence summary from the documents.",
        "source_refs": [
          {
            "doc_id": "doc_abc123",
            "file_name": "report.pdf",
            "page_or_section": "Page 3",
            "quote": "optional short quote"
          }
        ],
        "status": "confirmed",
        "confidence": "high"
      },
      "dimensions": [
        {
          "dimension_id": "d_001",
          "dimension_name": "Pricing Strategy",
          "items": [
            {
              "item_id": "i_002",
              "content": "Product A offers three tiers starting at $29/month.",
              "source_refs": [
                {
                  "doc_id": "doc_abc123",
                  "file_name": "report.pdf",
                  "page_or_section": "Page 5",
                  "quote": "Pricing starts at $29 per month for the Starter plan."
                }
              ],
              "status": "confirmed",
              "confidence": "high"
            }
          ]
        }
      ]
    }
  ],
  "conflicts_and_clarifications": []
}
```

If you find conflicting information about the same product and dimension, add an entry to `conflicts_and_clarifications` with `status` set to `conflict` on the related items.

## Source Documents

{documents_text}

Return only the JSON object, no additional explanation.
"""


class ExpertAgent:
    """Builds a competitive product knowledge base from source documents."""

    def __init__(
        self,
        model: str | None = None,
        api_key: str | None = None,
        use_rag: bool = True,
        rag_uri: str = "output/milvus_kb.db",
    ):
        from .llm_client import LLMClient

        self.client = LLMClient(api_key=api_key, model=model)
        self.use_rag = use_rag
        self.rag_uri = rag_uri
        self.rag_store: Any | None = None
        if self.use_rag:
            from .rag_store import RAGStore
            from .embeddings import EmbeddingModelCache

            self.rag_store = RAGStore(uri=rag_uri)
            EmbeddingModelCache().warmup()

    def build_knowledge_base(
        self,
        documents: list[ParsedDocument],
        kb_id: str | None = None,
        own_product_name: str | None = None,
    ) -> KnowledgeBase:
        """Build a knowledge base from parsed documents."""
        if not documents:
            raise ValueError("At least one document is required")

        kb_id = kb_id or f"kb_{uuid.uuid4().hex[:8]}"
        now = datetime.now().isoformat()

        prompt = self._create_extraction_prompt(documents)
        response = self._call_llm(prompt)
        extracted = self._parse_response(response)

        source_docs = [
            SourceDocument(
                doc_id=d.doc_id,
                file_name=d.file_name,
                file_type=d.file_type,
            )
            for d in documents
        ]

        products = [
            self._normalize_product(p, documents)
            for p in extracted.get("products", [])
        ]

        # Mark own product if requested
        own_product_id: str | None = None
        if own_product_name:
            target = own_product_name.strip().lower()
            for product in products:
                if product.product_name.strip().lower() == target:
                    product.is_own_product = True
                    own_product_id = product.product_id
                    break
            if own_product_id is None:
                print(f"   ⚠️ 未找到自有产品 '{own_product_name}'，请检查产品名称")

        conflicts = [
            ConflictRecord(**c)
            for c in extracted.get("conflicts_and_clarifications", [])
        ]

        kb = KnowledgeBase(
            knowledge_base_id=kb_id,
            created_at=now,
            updated_at=now,
            source_documents=source_docs,
            analyzed_products=[p.product_name for p in products],
            products=products,
            conflicts_and_clarifications=conflicts,
            own_product_id=own_product_id,
        )

        if self.rag_store is not None:
            self._index_knowledge_base(kb, documents)

        return kb

    def _index_knowledge_base(
        self, kb: KnowledgeBase, documents: list[ParsedDocument]
    ) -> None:
        """Index documents and facts into the RAG vector store."""
        if self.rag_store is None:
            return

        print("\n📦 正在建立 RAG 向量索引...")
        self.rag_store.clear()

        # Index raw document chunks
        for doc in documents:
            self.rag_store.add_document_chunks(
                doc_id=doc.doc_id,
                file_name=doc.file_name,
                chunks=doc.chunks,
            )

        # Index confirmed facts from the knowledge base
        for product in kb.products:
            for dim in product.dimensions:
                for item in dim.items:
                    if item.source_refs:
                        ref = item.source_refs[0]
                        self.rag_store.add_fact(
                            fact_content=item.content,
                            doc_id=ref.doc_id,
                            file_name=ref.file_name,
                            product_name=product.product_name,
                            dimension_name=dim.dimension_name,
                        )

        print("   RAG 索引完成")

    def _create_extraction_prompt(
        self, documents: list[ParsedDocument]
    ) -> str:
        doc_sections = []
        for doc in documents:
            header = f"--- Document: {doc.file_name} (doc_id: {doc.doc_id}, type: {doc.file_type}) ---"
            # Use chunks if text is very long; otherwise full text
            text = doc.text if len(doc.text) < 120_000 else "\n\n".join(doc.chunks[:5])
            doc_sections.append(f"{header}\n{text}")

        documents_text = "\n\n".join(doc_sections)
        return EXTRACTION_PROMPT.replace("{documents_text}", documents_text)

    def _call_llm(self, prompt: str) -> str:
        return self.client.chat_completion(
            prompt=prompt,
            system="You are a careful competitive intelligence analyst. You only use facts from the provided documents.",
            max_tokens=8000,
        )

    def _parse_response(self, response: str) -> dict[str, Any]:
        """Extract JSON from the LLM response."""
        try:
            return extract_json_block(response)
        except json.JSONDecodeError as exc:
            # Save the malformed response for debugging
            debug_path = f"output/debug_response_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
            try:
                import os
                os.makedirs("output", exist_ok=True)
                with open(debug_path, "w", encoding="utf-8") as f:
                    f.write(response)
            except Exception:
                pass
            raise ValueError(
                f"Could not parse LLM response as JSON: {exc}. "
                f"Full response saved to {debug_path}"
            ) from exc

    def _normalize_product(
        self, data: dict[str, Any], documents: list[ParsedDocument]
    ) -> ProductProfile:
        """Normalize a product dict into a ProductProfile model instance."""
        doc_map = {d.doc_id: d for d in documents}

        summary = data.get("summary")
        if summary:
            summary = FactItem(**summary)

        dimensions = []
        for dim in data.get("dimensions", []):
            items = [FactItem(**item) for item in dim.get("items", [])]
            # Validate source refs point to known documents
            for item in items:
                for ref in item.source_refs:
                    if ref.doc_id not in doc_map:
                        ref.doc_id = documents[0].doc_id
                        ref.file_name = documents[0].file_name
            dimensions.append(
                Dimension(
                    dimension_id=dim.get("dimension_id", f"d_{uuid.uuid4().hex[:6]}"),
                    dimension_name=dim["dimension_name"],
                    items=items,
                )
            )

        return ProductProfile(
            product_id=data.get("product_id", f"p_{uuid.uuid4().hex[:6]}"),
            product_name=data["product_name"],
            company_name=data.get("company_name"),
            summary=summary,
            dimensions=dimensions,
        )

    def supplement_with_search_results(
        self,
        kb: KnowledgeBase,
        search_results: list[SearchResult],
        original_documents: list[ParsedDocument],
    ) -> KnowledgeBase:
        """
        Merge web search findings into the knowledge base.

        For each fact discovered by the search agent, the expert agent checks
        the original documents to see if the fact can be confirmed or if it
        remains an external supplement. Conflicts are recorded for human review.

        Facts are verified in batches per product to reduce LLM round-trips.
        """
        print(f"\n📚 专家 Agent 正在把搜索结果补充进知识库...")
        print(f"   原始资料数: {len(original_documents)}")
        print(f"   搜索结果数: {len(search_results)}")

        # Group facts by product
        product_facts: dict[str, list[tuple[FactItem, str, ProductProfile]]] = {}
        for result in search_results:
            product = self._get_or_create_product(kb, result.product_name)
            if result.product_name not in kb.analyzed_products:
                kb.analyzed_products.append(result.product_name)

            entries = product_facts.setdefault(result.product_name, [])
            for fact in result.extracted_facts:
                dimension_name = self._extract_dimension_from_note(fact.note)
                entries.append((fact, dimension_name, product))

        # Verify facts in batches per product
        batch_size = 10
        for product_name, entries in product_facts.items():
            print(f"   正在验证产品 '{product_name}' 的 {len(entries)} 条事实...")
            for i in range(0, len(entries), batch_size):
                batch = entries[i : i + batch_size]
                self._verify_facts_batch(batch, original_documents)

            # Append verified facts to dimensions and record conflicts
            for fact, dimension_name, product in entries:
                dimension = self._get_or_create_dimension(product, dimension_name)
                dimension.items.append(fact)

                if fact.status == "conflict":
                    kb.conflicts_and_clarifications.append(
                        ConflictRecord(
                            conflict_id=f"c_{uuid.uuid4().hex[:8]}",
                            dimension=dimension_name,
                            product_id=product.product_id,
                            conflicting_items=[fact],
                        )
                    )

        kb.updated_at = datetime.now().isoformat()

        print(f"   补充完成，当前产品数: {len(kb.products)}")
        return kb

    def _get_or_create_product(
        self, kb: KnowledgeBase, product_name: str
    ) -> ProductProfile:
        """Find an existing product profile or create a new one."""
        for product in kb.products:
            if product.product_name.lower() == product_name.lower():
                return product

        new_product = ProductProfile(
            product_id=f"p_{uuid.uuid4().hex[:6]}",
            product_name=product_name,
        )
        kb.products.append(new_product)
        if product_name not in kb.analyzed_products:
            kb.analyzed_products.append(product_name)
        return new_product

    def _get_or_create_dimension(
        self, product: ProductProfile, dimension_name: str
    ) -> Dimension:
        """Find an existing dimension or create a new one."""
        for dim in product.dimensions:
            if dim.dimension_name.lower() == dimension_name.lower():
                return dim

        new_dim = Dimension(
            dimension_id=f"d_{uuid.uuid4().hex[:6]}",
            dimension_name=dimension_name,
        )
        product.dimensions.append(new_dim)
        return new_dim

    def _extract_dimension_from_note(self, note: str | None) -> str:
        """Extract dimension_name from a fact note like 'dimension: 定价策略'."""
        if not note:
            return "其他信息"
        prefix = "dimension:"
        if prefix in note:
            return note.split(prefix, 1)[1].strip() or "其他信息"
        return note.strip() or "其他信息"

    def _keyword_retrieve(
        self,
        fact: FactItem,
        documents: list[ParsedDocument],
        top_k: int = 3,
    ) -> list[tuple[ParsedDocument, str]]:
        """Fallback keyword-based chunk retrieval."""
        keywords = self._extract_keywords(fact.content)
        if not keywords:
            return []

        scored: list[tuple[ParsedDocument, str, int]] = []
        for doc in documents:
            for chunk in doc.chunks:
                score = self._score_chunk(chunk, keywords)
                scored.append((doc, chunk, score))

        scored.sort(key=lambda x: x[2], reverse=True)
        return [(doc, chunk) for doc, chunk, _ in scored[:top_k] if _ > 0]

    def _extract_keywords(self, text: str) -> list[str]:
        """Extract simple keywords from text for relevance matching."""
        import re

        # Chinese phrases (2+ chars) and English/alphanumeric words (2+ chars)
        candidates = re.findall(r"[一-鿿]{2,}|[a-zA-Z0-9]{2,}", text)
        # Deduplicate while preserving order
        seen = set()
        keywords = []
        for kw in candidates:
            kw_lower = kw.lower()
            if kw_lower not in seen and len(kw_lower) >= 2:
                seen.add(kw_lower)
                keywords.append(kw)
        return keywords

    def _score_chunk(
        self, chunk: str, keywords: list[str]
    ) -> int:
        """Score a chunk by keyword overlap with the fact."""
        score = 0
        chunk_lower = chunk.lower()
        for kw in keywords:
            if kw.lower() in chunk_lower:
                score += 1

        # Boost if chunk mentions the product name (heuristic from fact content)
        # Simple approach: give extra weight to chunks containing any 4+ char keyword
        for kw in keywords:
            if len(kw) >= 4 and kw.lower() in chunk_lower:
                score += 1

        return score

    def _verify_facts_batch(
        self,
        entries: list[tuple[FactItem, str, ProductProfile]],
        documents: list[ParsedDocument],
    ) -> None:
        """Verify a batch of facts for the same product in one LLM call."""
        if not entries:
            return

        # Build combined query for RAG retrieval
        combined_query = " ".join(fact.content for fact, _, _ in entries)
        relevant_chunks = self._retrieve_chunks_for_query(
            combined_query, documents, top_k=5
        )
        if relevant_chunks:
            doc_sections = []
            for doc, chunk in relevant_chunks:
                header = f"--- Document: {doc.file_name} (doc_id: {doc.doc_id}) ---"
                doc_sections.append(f"{header}\n{chunk}")
            documents_text = "\n\n".join(doc_sections)
        else:
            documents_text = "[无相关原始资料片段]"

        facts_text = ""
        fact_map: dict[str, tuple[FactItem, str]] = {}
        for idx, (fact, dimension_name, _) in enumerate(entries, start=1):
            facts_text += f"{idx}. [{fact.item_id}] {fact.content} (维度: {dimension_name})\n"
            fact_map[fact.item_id] = (fact, dimension_name)

        template = """You are a strict fact-checking assistant for competitive intelligence.

Your task: For each web-discovered fact below, determine whether it is supported by, contradicted by, or absent from the provided source document chunks.

## Relevant Source Document Chunks

Below are the most relevant excerpts from the original source documents. Use only these excerpts for your judgment.

{documents_text}

## Web-Discovered Facts

{facts_text}

## Instructions

1. For each fact, search only the provided document chunks for related information.
2. If the chunks clearly support the fact, return `status: "confirmed"`.
3. If the chunks clearly contradict the fact, return `status: "conflict"`.
4. If the chunks do not mention this information at all, return `status: "external_supplement"`.
5. If the chunks mention related information but it is unclear, return `status: "pending_verification"`.
6. Do not use your own general knowledge; only compare the facts against the provided document chunks.

## Output Format

Return a JSON array with one object per input fact, preserving order:

```json
[
  {
    "item_id": "i_001",
    "status": "confirmed" or "external_supplement" or "conflict" or "pending_verification",
    "evidence": "Relevant quote or summary from the document chunks, or '未找到' if absent",
    "source_doc_id": "doc_id of the supporting document, or empty string",
    "source_file_name": "file_name of the supporting document, or empty string",
    "note": "Brief explanation of the decision"
  }
]
```

Return only the JSON array, no additional explanation.
"""
        prompt = (
            template.replace("{documents_text}", documents_text)
            .replace("{facts_text}", facts_text)
        )

        response = self._call_llm(prompt)
        try:
            verdicts = extract_json_block(response)
            if not isinstance(verdicts, list):
                raise ValueError("Response is not a JSON array")
        except (json.JSONDecodeError, ValueError) as exc:
            print(f"   ⚠️ 无法解析批量验证结果: {exc}")
            for fact, dimension_name, _ in entries:
                fact.status = "external_supplement"
                fact.note = f"批量验证失败，保留为外部补充 | 维度: {dimension_name}"
            return

        for verdict in verdicts:
            item_id = verdict.get("item_id")
            if item_id not in fact_map:
                continue

            fact, dimension_name = fact_map[item_id]
            status = verdict.get("status", "external_supplement")
            fact.status = status if status in {
                "confirmed",
                "external_supplement",
                "conflict",
                "pending_verification",
            } else "external_supplement"

            if fact.status == "confirmed":
                evidence = verdict.get("evidence", "").strip()
                doc_id = verdict.get("source_doc_id", "").strip()
                file_name = verdict.get("source_file_name", "").strip()
                if evidence and evidence != "未找到" and file_name:
                    fact.source_refs.append(
                        SourceRef(
                            doc_id=doc_id or "unknown",
                            file_name=file_name,
                            page_or_section="",
                            quote=evidence[:500],
                            location_hint="verified against original documents",
                        )
                    )
                fact.confidence = "high"
            elif fact.status == "conflict":
                fact.confidence = "low"

            note_parts = [f"维度: {dimension_name}"]
            if verdict.get("note"):
                note_parts.append(verdict["note"])
            if fact.status == "external_supplement":
                note_parts.append("来源：网页搜索")
            fact.note = " | ".join(note_parts)

    def _retrieve_chunks_for_query(
        self, query: str, documents: list[ParsedDocument], top_k: int = 5
    ) -> list[tuple[ParsedDocument, str]]:
        """Retrieve chunks relevant to an arbitrary query string."""
        if self.rag_store is not None:
            chunks = self.rag_store.retrieve(query, top_k=top_k)
            if chunks:
                doc_map = {d.doc_id: d for d in documents}
                result = []
                for chunk in chunks:
                    doc = doc_map.get(chunk.doc_id)
                    if doc is None:
                        doc = ParsedDocument(
                            doc_id=chunk.doc_id,
                            file_name=chunk.file_name,
                            file_type=".rag",
                            text=chunk.chunk_text,
                        )
                    result.append((doc, chunk.chunk_text))
                return result

        # Fallback to keyword retrieval using the query as a synthetic fact
        synthetic_fact = FactItem(
            item_id="synthetic",
            content=query,
            source_refs=[],
        )
        return self._keyword_retrieve(synthetic_fact, documents, top_k)
