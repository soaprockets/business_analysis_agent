"""
Analysis agent that compares competitive products using a populated KnowledgeBase.

It aligns dynamically discovered dimensions across products, builds a comparison
matrix, scores products quantitatively, and produces SWOT, gap analysis, and
prioritized recommendations.
"""

import json
import os
import uuid
from datetime import datetime
from typing import Any, Optional

from .models import (
    AnalysisReport,
    ComparisonCell,
    ComparisonDimension,
    ComparisonMatrix,
    CriterionScore,
    FactItem,
    GapItem,
    KnowledgeBase,
    ProductProfile,
    ProductScore,
    RecommendationItem,
    ScoreCriterion,
    SwotItem,
)
from .utils import extract_json_block


class AnalysisAgent:
    """Competitive analysis agent."""

    DEFAULT_CRITERIA: list[ScoreCriterion] = [
        ScoreCriterion(
            criterion_id="function",
            name="功能完整性",
            description="产品功能覆盖的广度和深度，是否满足目标场景需求",
            weight=0.20,
        ),
        ScoreCriterion(
            criterion_id="pricing",
            name="定价竞争力",
            description="价格透明度、性价比、目标客户的可承受度",
            weight=0.15,
        ),
        ScoreCriterion(
            criterion_id="usability",
            name="易用性",
            description="上手难度、界面友好度、移动端体验、培训成本",
            weight=0.15,
        ),
        ScoreCriterion(
            criterion_id="analytics",
            name="数据分析能力",
            description="报表、BI、自定义仪表盘、预测能力",
            weight=0.15,
        ),
        ScoreCriterion(
            criterion_id="integration",
            name="集成能力",
            description="与第三方办公/ERP/通讯工具的集成广度与深度",
            weight=0.10,
        ),
        ScoreCriterion(
            criterion_id="deployment",
            name="部署灵活性",
            description="SaaS、私有化部署、实施周期、合规支持",
            weight=0.10,
        ),
        ScoreCriterion(
            criterion_id="market_fit",
            name="目标市场匹配度",
            description="定位清晰度、目标客户覆盖、行业口碑",
            weight=0.10,
        ),
        ScoreCriterion(
            criterion_id="ai_auto",
            name="AI / 自动化能力",
            description="AI 辅助、自动化工作流、智能预测等先进能力",
            weight=0.05,
        ),
    ]

    def __init__(
        self,
        model: str | None = None,
        api_key: str | None = None,
        criteria: list[ScoreCriterion] | None = None,
    ):
        from .llm_client import LLMClient

        self.client = LLMClient(api_key=api_key, model=model)
        self.criteria = criteria or self.DEFAULT_CRITERIA

    def analyze(self, kb: KnowledgeBase) -> AnalysisReport:
        """Run the full competitive analysis pipeline."""
        print("\n📊 分析 Agent 正在生成竞争分析报告...")

        own_product = self._find_own_product(kb)
        own_product_id = own_product.product_id if own_product else None
        own_product_name = own_product.product_name if own_product else None

        if own_product:
            print(f"   自有产品：{own_product_name}")
        else:
            print("   未标记自有产品，将生成竞品互相对比分析")

        print(f"   分析产品数：{len(kb.products)}")

        # Step 1: align dimensions across products
        aligned_dims, mapping = self._align_dimensions(kb.products)
        print(f"   对齐后维度数：{len(aligned_dims)}")

        # Step 2: build comparison matrix deterministically
        matrix = self._build_comparison_matrix(kb, aligned_dims, mapping)
        print(f"   对比矩阵单元格：{len(matrix.cells)}")

        # Step 3: score products quantitatively
        scores = self._score_products(kb, matrix, own_product_id)
        print(f"   评分完成，排名第一：{scores[0].product_name if scores else '无'}")

        # Step 4: generate SWOT, gaps, recommendations
        swot, gaps, recommendations = self._generate_strategic_analysis(
            kb, matrix, scores, own_product_id
        )
        print(f"   SWOT：{len(swot)} 条，差距：{len(gaps)} 条，建议：{len(recommendations)} 条")

        return AnalysisReport(
            report_id=f"ar_{uuid.uuid4().hex[:8]}",
            created_at=datetime.now().isoformat(),
            own_product_id=own_product_id,
            comparison_matrix=matrix,
            product_scores=scores,
            swot=swot,
            gaps=gaps,
            recommendations=recommendations,
        )

    def _find_own_product(self, kb: KnowledgeBase) -> Optional[ProductProfile]:
        """Identify the product marked as our own."""
        if kb.own_product_id:
            for product in kb.products:
                if product.product_id == kb.own_product_id:
                    return product
        for product in kb.products:
            if product.is_own_product:
                return product
        return None

    def _align_dimensions(
        self, products: list[ProductProfile]
    ) -> tuple[list[ComparisonDimension], dict[str, str]]:
        """Cluster semantically equivalent dimensions into canonical dimensions."""
        if not products:
            return [], {}

        # Collect all original dimensions
        dim_inputs: list[dict[str, Any]] = []
        for product in products:
            for dim in product.dimensions:
                dim_inputs.append({
                    "product_id": product.product_id,
                    "dimension_id": dim.dimension_id,
                    "dimension_name": dim.dimension_name,
                })

        if len(dim_inputs) <= 1:
            # No alignment needed
            dims = [
                ComparisonDimension(
                    dimension_id=f"cd_{uuid.uuid4().hex[:6]}",
                    dimension_name=d["dimension_name"],
                    original_dimension_names=[d["dimension_name"]],
                )
                for d in dim_inputs
            ]
            mapping = {d.dimension_name.lower(): d.dimension_id for d in dims}
            return dims, mapping

        prompt = self._build_alignment_prompt(dim_inputs)
        response = self._call_llm(prompt, max_tokens=4000)

        try:
            data = extract_json_block(response)
        except json.JSONDecodeError as exc:
            print(f"   ⚠️ 维度对齐结果解析失败：{exc}")
            # Fallback: treat every original dimension as canonical
            dims = [
                ComparisonDimension(
                    dimension_id=f"cd_{uuid.uuid4().hex[:6]}",
                    dimension_name=d["dimension_name"],
                    original_dimension_names=[d["dimension_name"]],
                )
                for d in dim_inputs
            ]
            mapping = {d["dimension_name"].lower(): d["dimension_id"] for d in dim_inputs}
            return dims, mapping

        canonical_dims: list[ComparisonDimension] = []
        for cd in data.get("canonical_dimensions", []):
            canonical_dims.append(
                ComparisonDimension(
                    dimension_id=cd.get("dimension_id") or f"cd_{uuid.uuid4().hex[:6]}",
                    dimension_name=cd.get("dimension_name", "未命名维度"),
                    description=cd.get("description"),
                    original_dimension_names=cd.get("original_dimension_names", []),
                )
            )

        # Build mapping from original dimension name -> canonical dimension id
        mapping: dict[str, str] = {}
        for cd in canonical_dims:
            for raw_name in cd.original_dimension_names:
                mapping[raw_name.lower().strip()] = cd.dimension_id

        return canonical_dims, mapping

    def _build_alignment_prompt(self, dim_inputs: list[dict[str, Any]]) -> str:
        template = """You are a competitive intelligence analyst. Your task is to group the following product dimensions into canonical comparison dimensions.

Dimensions that describe the same aspect of a product should be merged into one canonical dimension. Be concise but accurate.

## Input Dimensions

{dimensions_json}

## Instructions

1. Return a JSON object with a single key `canonical_dimensions`.
2. Each canonical dimension must have:
   - `dimension_id`: a short unique ID like "cd_001"
   - `dimension_name`: a clear, human-readable name in Chinese
   - `description`: one sentence explaining what the dimension covers
   - `original_dimension_names`: list of raw dimension names from the input that map to this canonical dimension
3. Every input `dimension_name` must appear in exactly one `original_dimension_names` list.
4. Do not add explanations outside the JSON.
5. **CRITICAL**: Return valid JSON only. Do not include markdown code blocks, trailing commas, unescaped quotes, or raw line breaks inside JSON string values. Escape all special characters properly (e.g., `\"`, `\\`, `\\n`).

## Output Format

```json
{
  "canonical_dimensions": [
    {
      "dimension_id": "cd_001",
      "dimension_name": "目标用户与定位",
      "description": "产品的目标客户群、市场定位与价值主张",
      "original_dimension_names": ["定位与目标用户", "目标客户群"]
    }
  ]
}
```
"""
        return template.replace("{dimensions_json}", json.dumps(dim_inputs, ensure_ascii=False, indent=2))

    def _build_comparison_matrix(
        self,
        kb: KnowledgeBase,
        aligned_dims: list[ComparisonDimension],
        mapping: dict[str, str],
    ) -> ComparisonMatrix:
        """Build the comparison matrix by grouping facts under canonical dimensions."""
        cells: list[ComparisonCell] = []
        product_ids: list[str] = [p.product_id for p in kb.products]

        for product in kb.products:
            for dim in product.dimensions:
                canonical_id = mapping.get(dim.dimension_name.lower().strip())
                if not canonical_id:
                    continue

                facts = [item for item in dim.items if item.content.strip()]
                if not facts:
                    continue

                summary = self._synthesize_facts(facts)
                status_summary = self._summarize_statuses(facts)
                confidence = self._aggregate_confidence(facts)

                cells.append(
                    ComparisonCell(
                        cell_id=f"cell_{uuid.uuid4().hex[:8]}",
                        dimension_id=canonical_id,
                        product_id=product.product_id,
                        summary=summary,
                        fact_ids=[f.item_id for f in facts],
                        status_summary=status_summary,
                        confidence=confidence,
                    )
                )

        return ComparisonMatrix(
            dimensions=aligned_dims,
            cells=cells,
            product_ids=product_ids,
        )

    def _synthesize_facts(self, facts: list[FactItem]) -> str:
        """Create a short summary from a list of facts."""
        contents = [f.content.strip() for f in facts if f.content.strip()]
        if not contents:
            return "无可用信息"
        if len(contents) == 1:
            return contents[0]
        # Join multiple facts with numbering, keep it concise
        combined = " ".join(contents)
        if len(combined) <= 300:
            return combined
        return combined[:297] + "..."

    def _summarize_statuses(self, facts: list[FactItem]) -> str:
        """Summarize fact statuses, e.g. 'confirmed x2, external_supplement x1'."""
        counts: dict[str, int] = {}
        for fact in facts:
            counts[fact.status] = counts.get(fact.status, 0) + 1
        parts = [f"{status} x{count}" for status, count in counts.items()]
        return ", ".join(parts) if parts else "unknown"

    def _aggregate_confidence(self, facts: list[FactItem]) -> str:
        """Aggregate confidence across facts."""
        if not facts:
            return "low"
        high = sum(1 for f in facts if f.confidence == "high")
        medium = sum(1 for f in facts if f.confidence == "medium")
        low = sum(1 for f in facts if f.confidence == "low")
        if low > high + medium:
            return "low"
        if high >= medium + low:
            return "high"
        return "medium"

    def _score_products(
        self,
        kb: KnowledgeBase,
        matrix: ComparisonMatrix,
        own_product_id: Optional[str],
    ) -> list[ProductScore]:
        """Score each product across criteria using one LLM call."""
        product_map = {p.product_id: p for p in kb.products}

        prompt = self._build_scoring_prompt(matrix, own_product_id)
        response = self._call_llm(prompt, max_tokens=8000)

        try:
            data = extract_json_block(response)
        except json.JSONDecodeError as exc:
            print(f"   ⚠️ 评分结果解析失败：{exc}")
            data = []

        if not isinstance(data, list):
            data = data.get("product_scores", []) if isinstance(data, dict) else []

        # Normalize and compute total scores
        scores: list[ProductScore] = []
        for raw in data:
            product_id = raw.get("product_id", "")
            product = product_map.get(product_id)
            if not product:
                continue

            criterion_scores: list[CriterionScore] = []
            total_weight = 0.0
            weighted_sum = 0.0

            for raw_cs in raw.get("criterion_scores", []):
                criterion = self._find_criterion(raw_cs.get("criterion_id", ""))
                weight = criterion.weight if criterion else 0.0
                score = float(raw_cs.get("score", 5.0))
                criterion_scores.append(
                    CriterionScore(
                        criterion_id=raw_cs.get("criterion_id", ""),
                        score=score,
                        rationale=raw_cs.get("rationale", ""),
                        fact_ids=raw_cs.get("fact_ids", []),
                    )
                )
                weighted_sum += score * weight
                total_weight += weight

            total_score = weighted_sum / total_weight if total_weight > 0 else 0.0

            scores.append(
                ProductScore(
                    product_id=product_id,
                    product_name=product.product_name,
                    total_score=round(total_score, 2),
                    rank=0,  # assigned after sorting
                    criterion_scores=criterion_scores,
                    overall_rationale=raw.get("overall_rationale", ""),
                )
            )

        # Sort by total score descending and assign ranks
        scores.sort(key=lambda x: x.total_score, reverse=True)
        for idx, score in enumerate(scores, start=1):
            score.rank = idx

        return scores

    def _find_criterion(self, criterion_id: str) -> Optional[ScoreCriterion]:
        for criterion in self.criteria:
            if criterion.criterion_id == criterion_id:
                return criterion
        return None

    def _build_scoring_prompt(
        self, matrix: ComparisonMatrix, own_product_id: Optional[str]
    ) -> str:
        own_product_note = ""
        if own_product_id:
            own_product_note = f"自有产品 ID：{own_product_id}\n请特别关注自有产品与竞品的对比。"

        criteria_json = json.dumps(
            [c.model_dump() for c in self.criteria],
            ensure_ascii=False,
            indent=2,
        )
        matrix_json = json.dumps(
            matrix.model_dump(mode="json"),
            ensure_ascii=False,
            indent=2,
        )

        template = """You are a strict competitive intelligence analyst. Score each product on the criteria below using only the provided comparison matrix facts.

{own_product_note}

## Scoring Criteria

{criteria_json}

## Comparison Matrix

{matrix_json}

## Instructions

1. For each product and each criterion, assign a score from 1 to 10.
2. Provide a concise rationale for each score and cite relevant `fact_ids` from the matrix cells.
3. Compute the `total_score` as the weighted average of criterion scores using the provided weights. You do not need to include the total in the JSON; the caller will compute it.
4. Return a JSON array of product scores.

## Output Format

```json
[
  {
    "product_id": "p_xxx",
    "product_name": "Product Name",
    "criterion_scores": [
      {
        "criterion_id": "function",
        "score": 8.5,
        "rationale": " Covers core CRM features well but lacks advanced BI.",
        "fact_ids": ["i_001", "i_002"]
      }
    ],
    "overall_rationale": "Overall competitive position summary."
  }
]
```

Return only the JSON array, no extra explanation.

**CRITICAL JSON REQUIREMENTS**:
- Output must be a single valid JSON array, with no markdown code blocks and no text outside the array.
- All string values must be on a single line; do not include raw line breaks. Use `\n` to represent newlines if necessary.
- Escape all double quotes inside strings as `\"` and backslashes as `\\`.
- Do not use trailing commas after the last element in arrays or objects.
"""
        return (
            template.replace("{own_product_note}", own_product_note)
            .replace("{criteria_json}", criteria_json)
            .replace("{matrix_json}", matrix_json)
        )

    def _generate_strategic_analysis(
        self,
        kb: KnowledgeBase,
        matrix: ComparisonMatrix,
        scores: list[ProductScore],
        own_product_id: Optional[str],
    ) -> tuple[list[SwotItem], list[GapItem], list[RecommendationItem]]:
        """Generate SWOT, gaps, and recommendations in one LLM call."""
        prompt = self._build_strategic_prompt(kb, matrix, scores, own_product_id)
        response = self._call_llm(prompt, max_tokens=8000)

        try:
            data = extract_json_block(response)
        except json.JSONDecodeError as exc:
            print(f"   ⚠️ 战略分析结果解析失败：{exc}")
            data = {"swot": [], "gaps": [], "recommendations": []}

        if not isinstance(data, dict):
            data = {"swot": [], "gaps": [], "recommendations": []}

        swot = self._parse_swot(data.get("swot", []))
        gaps = self._parse_gaps(data.get("gaps", []), own_product_id)
        recommendations = self._parse_recommendations(data.get("recommendations", []))

        return swot, gaps, recommendations

    def _build_strategic_prompt(
        self,
        kb: KnowledgeBase,
        matrix: ComparisonMatrix,
        scores: list[ProductScore],
        own_product_id: Optional[str],
    ) -> str:
        own_product_note = ""
        if own_product_id:
            own = next((p for p in kb.products if p.product_id == own_product_id), None)
            if own:
                own_product_note = f"自有产品：{own.product_name}（ID: {own_product_id}）。SWOT、差距分析和建议应主要从自有产品视角出发，对比竞品。"
        else:
            own_product_note = "未标记自有产品。请从全局视角为各产品生成 SWOT、差距对比和建议。"

        matrix_json = json.dumps(
            matrix.model_dump(mode="json"),
            ensure_ascii=False,
            indent=2,
        )
        scores_json = json.dumps(
            [s.model_dump(mode="json") for s in scores],
            ensure_ascii=False,
            indent=2,
        )

        template = """You are a senior strategy consultant. Based on the comparison matrix and product scores below, produce a structured strategic analysis.

{own_product_note}

## Comparison Matrix

{matrix_json}

## Product Scores

{scores_json}

## Instructions

1. **SWOT**: List strengths, weaknesses, opportunities, and threats. Each item must relate to specific products and cite `fact_ids` where possible.
2. **Gap Analysis**: Identify areas where the own product (or a trailing product, if no own product) underperforms compared to competitors. Include impact level (high/medium/low).
3. **Recommendations**: Derive prioritized actions from gaps and opportunities. Each recommendation must have priority (high/medium/low), title, description, rationale, and expected impact.
4. Return only JSON in the format below.

**CRITICAL JSON REQUIREMENTS**:
- Output must be a single valid JSON object, with no markdown code blocks and no text outside the object.
- All string values must be on a single line; do not include raw line breaks. Use `\n` to represent newlines if necessary.
- Escape all double quotes inside strings as `\"` and backslashes as `\\`.
- Do not use trailing commas after the last element in arrays or objects.
- Ensure every opening bracket/brace has a matching closing bracket/brace.

## Output Format

```json
{
  "swot": [
    {
      "category": "strength",
      "content": "Statement",
      "related_product_ids": ["p_xxx"],
      "dimension_id": "cd_xxx",
      "fact_ids": ["i_xxx"]
    }
  ],
  "gaps": [
    {
      "dimension_id": "cd_xxx",
      "description": "Own product lacks X while competitors provide Y.",
      "impact": "high",
      "compared_to_product_ids": ["p_yyy"],
      "fact_ids": ["i_xxx"]
    }
  ],
  "recommendations": [
    {
      "priority": "high",
      "title": "Short title",
      "description": "Detailed action",
      "rationale": "Why this matters",
      "expected_impact": "Expected outcome",
      "dimension_id": "cd_xxx",
      "related_product_ids": ["p_xxx"],
      "related_gap_ids": ["g_xxx"]
    }
  ]
}
```
"""
        return (
            template.replace("{own_product_note}", own_product_note)
            .replace("{matrix_json}", matrix_json)
            .replace("{scores_json}", scores_json)
        )

    def _parse_swot(self, data: list[Any]) -> list[SwotItem]:
        items: list[SwotItem] = []
        for raw in data:
            if not isinstance(raw, dict):
                continue
            items.append(
                SwotItem(
                    item_id=raw.get("item_id") or f"swot_{uuid.uuid4().hex[:6]}",
                    category=raw.get("category", "strength").lower(),
                    content=raw.get("content", ""),
                    related_product_ids=raw.get("related_product_ids", []),
                    dimension_id=raw.get("dimension_id"),
                    fact_ids=raw.get("fact_ids", []),
                )
            )
        return items

    def _parse_gaps(
        self, data: list[Any], own_product_id: Optional[str]
    ) -> list[GapItem]:
        items: list[GapItem] = []
        for raw in data:
            if not isinstance(raw, dict):
                continue
            items.append(
                GapItem(
                    item_id=raw.get("item_id") or f"gap_{uuid.uuid4().hex[:6]}",
                    dimension_id=raw.get("dimension_id"),
                    description=raw.get("description", ""),
                    impact=raw.get("impact", "medium").lower(),
                    own_product_id=raw.get("own_product_id") or own_product_id,
                    compared_to_product_ids=raw.get("compared_to_product_ids", []),
                    fact_ids=raw.get("fact_ids", []),
                )
            )
        return items

    def _parse_recommendations(self, data: list[Any]) -> list[RecommendationItem]:
        items: list[RecommendationItem] = []
        for raw in data:
            if not isinstance(raw, dict):
                continue
            items.append(
                RecommendationItem(
                    item_id=raw.get("item_id") or f"rec_{uuid.uuid4().hex[:6]}",
                    priority=raw.get("priority", "medium").lower(),
                    title=raw.get("title", ""),
                    description=raw.get("description", ""),
                    rationale=raw.get("rationale", ""),
                    related_gap_ids=raw.get("related_gap_ids", []),
                    related_product_ids=raw.get("related_product_ids", []),
                    dimension_id=raw.get("dimension_id"),
                    expected_impact=raw.get("expected_impact"),
                )
            )
        return items

    def _call_llm(self, prompt: str, max_tokens: int, system: str | None = None) -> str:
        return self.client.chat_completion(
            prompt=prompt,
            system=system or "You are a careful competitive intelligence analyst. Only use facts from the provided data.",
            max_tokens=max_tokens,
        )
