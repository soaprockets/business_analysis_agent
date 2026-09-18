"""
Report expert agent that synthesizes the knowledge base and analysis results
into a polished, structured competitive analysis report.
"""

import json
import os
import uuid
from datetime import datetime
from typing import Any

from .llm_client import LLMClient
from .models import (
    AnalysisReport,
    KeyFinding,
    KnowledgeBase,
    ProductPosition,
    ReportOutput,
)


class ReportAgent:
    """Generates the final structured competitive analysis report."""

    def __init__(
        self,
        model: str | None = None,
        api_key: str | None = None,
    ):
        self.client = LLMClient(api_key=api_key, model=model)

    def generate_report(self, kb: KnowledgeBase) -> ReportOutput:
        """Synthesize a structured report from the knowledge base and analysis."""
        print("\n📝 报告专家 Agent 正在生成最终竞品分析报告...")

        if not kb.analysis:
            print("   警告：知识库尚未运行分析，将基于原始知识库生成简要报告")

        prompt = self._build_report_prompt(kb)
        response = self.client.chat_completion(
            prompt=prompt,
            system="You are a senior product strategy consultant. Synthesize the provided data into a clear, structured, and actionable competitive analysis report in Chinese.",
            max_tokens=8000,
        )

        try:
            data = self._parse_json_response(response)
        except json.JSONDecodeError as exc:
            print(f"   ⚠️ 报告解析失败：{exc}")
            data = {}

        return self._build_report_output(data, kb)

    def _build_report_prompt(self, kb: KnowledgeBase) -> str:
        """Build the prompt for the report generation LLM call."""
        own_product_name = "未标记"
        if kb.own_product_id:
            own = next(
                (p for p in kb.products if p.product_id == kb.own_product_id), None
            )
            own_product_name = own.product_name if own else kb.own_product_id

        # Compact KB summary
        kb_summary = self._summarize_kb(kb)
        analysis_summary = self._summarize_analysis(kb)

        template = """You are a report expert agent. Based on the following knowledge base and analysis results, generate a structured competitive product analysis report in Chinese.

## Own Product

{own_product_name}

## Knowledge Base Summary

{kb_summary}

## Analysis Results Summary

{analysis_summary}

## Instructions

1. Write the report in professional Chinese.
2. Synthesize facts into insights; do not simply list raw facts.
3. Return a JSON object matching the schema below.
4. The `full_markdown` field should contain a complete, publication-ready Markdown report with clear sections.

## Output Schema

```json
{
  "title": "竞品分析报告标题",
  "executive_summary": "高层摘要，3-5 句话",
  "market_overview": "市场格局与竞争态势概述",
  "product_positions": [
    {
      "product_id": "p_xxx",
      "product_name": "Product Name",
      "positioning": "该产品在市场中的定位 paragraph",
      "key_strengths": ["优势1", "优势2"],
      "key_weaknesses": ["劣势1", "劣势2"]
    }
  ],
  "key_findings": [
    {
      "finding_id": "f_001",
      "title": "发现标题",
      "detail": "详细说明",
      "evidence": ["证据1", "证据2"],
      "related_product_ids": ["p_xxx"],
      "related_dimension_ids": ["cd_xxx"]
    }
  ],
  "swot_summary": "SWOT 综合叙述",
  "gap_summary": "差距分析综合叙述",
  "strategic_recommendations": ["建议1", "建议2"],
  "risk_and_conflicts": "风险、信息冲突与局限性说明",
  "next_steps": ["下一步行动1", "下一步行动2"],
  "full_markdown": "完整的 Markdown 报告文本"
}
```

注意：如果知识库中已经包含 `AnalysisReport`，`swot_summary`、`gap_summary`、`strategic_recommendations` 会由分析结果自动推导并覆盖你返回的内容；你无需在这三个字段上过度展开。请把重点放在 `executive_summary`、`market_overview`、`product_positions`、`key_findings`、`risk_and_conflicts`、`next_steps` 和 `full_markdown` 上。

Return only the JSON object, no extra explanation.
"""
        return (
            template.replace("{own_product_name}", own_product_name)
            .replace("{kb_summary}", kb_summary)
            .replace("{analysis_summary}", analysis_summary)
        )

    def _summarize_kb(self, kb: KnowledgeBase) -> str:
        """Create a concise text summary of the knowledge base."""
        lines: list[str] = []
        lines.append(f"知识库 ID：{kb.knowledge_base_id}")
        lines.append(f"来源文档：{len(kb.source_documents)} 份")
        lines.append(f"分析产品：{', '.join(kb.analyzed_products)}")
        lines.append("")

        for product in kb.products:
            lines.append(f"### {product.product_name}")
            if product.company_name:
                lines.append(f"所属公司：{product.company_name}")
            if product.summary:
                lines.append(f"摘要：{product.summary.content}")
            for dim in product.dimensions:
                lines.append(f"- {dim.dimension_name}:")
                for item in dim.items:
                    lines.append(f"  - [{item.status}/{item.confidence}] {item.content}")
            lines.append("")

        if kb.conflicts_and_clarifications:
            lines.append("### 信息冲突")
            for conflict in kb.conflicts_and_clarifications:
                items_summary = " / ".join(
                    item.content[:60] for item in conflict.conflicting_items
                )
                lines.append(f"- {conflict.dimension}: {items_summary}")

        return "\n".join(lines)

    def _summarize_analysis(self, kb: KnowledgeBase) -> str:
        """Create a concise text summary of the analysis results."""
        if not kb.analysis:
            return "暂无分析结果。"

        analysis = kb.analysis
        lines: list[str] = []

        lines.append("### 对比矩阵")
        product_map = {p.product_id: p for p in kb.products}
        for dim in analysis.comparison_matrix.dimensions:
            lines.append(f"- {dim.dimension_name}")
            for cell in analysis.comparison_matrix.cells:
                if cell.dimension_id == dim.dimension_id:
                    product_name = product_map.get(cell.product_id, cell).product_name
                    lines.append(f"  - {product_name}: {cell.summary}")

        lines.append("\n### 量化评分")
        for score in sorted(analysis.product_scores, key=lambda s: s.rank):
            lines.append(f"- #{score.rank} {score.product_name}: {score.total_score}")
            for cs in score.criterion_scores:
                lines.append(f"  - {cs.criterion_id}: {cs.score}")

        lines.append("\n### SWOT")
        for item in analysis.swot:
            lines.append(f"- [{item.category}] {item.content}")

        lines.append("\n### 差距")
        for gap in analysis.gaps:
            lines.append(f"- [{gap.impact}] {gap.description}")

        lines.append("\n### 建议")
        for rec in analysis.recommendations:
            lines.append(f"- [{rec.priority}] {rec.title}: {rec.description}")

        return "\n".join(lines)

    def _parse_json_response(self, response: str) -> dict[str, Any]:
        """Extract JSON from the LLM response."""
        from .utils import extract_json_block

        return extract_json_block(response)

    def _build_report_output(
        self, data: dict[str, Any], kb: KnowledgeBase
    ) -> ReportOutput:
        """Build a ReportOutput from parsed LLM response with safe fallbacks."""
        product_positions: list[ProductPosition] = []
        for raw in data.get("product_positions", []):
            if not isinstance(raw, dict):
                continue
            product_positions.append(
                ProductPosition(
                    product_id=raw.get("product_id", ""),
                    product_name=raw.get("product_name", ""),
                    positioning=raw.get("positioning", ""),
                    key_strengths=raw.get("key_strengths", []),
                    key_weaknesses=raw.get("key_weaknesses", []),
                )
            )

        key_findings: list[KeyFinding] = []
        for raw in data.get("key_findings", []):
            if not isinstance(raw, dict):
                continue
            key_findings.append(
                KeyFinding(
                    finding_id=raw.get("finding_id") or f"f_{uuid.uuid4().hex[:6]}",
                    title=raw.get("title", ""),
                    detail=raw.get("detail", ""),
                    evidence=raw.get("evidence", []),
                    related_product_ids=raw.get("related_product_ids", []),
                    related_dimension_ids=raw.get("related_dimension_ids", []),
                )
            )

        # Derive/overlap strategic content from structured analysis when available
        swot_summary = data.get("swot_summary", "")
        gap_summary = data.get("gap_summary", "")
        strategic_recommendations = data.get("strategic_recommendations", [])
        if kb.analysis:
            swot_summary = self._derive_swot_summary(kb.analysis) or swot_summary
            gap_summary = self._derive_gap_summary(kb.analysis) or gap_summary
            derived_recommendations = self._derive_strategic_recommendations(kb.analysis)
            strategic_recommendations = derived_recommendations or strategic_recommendations
            if not key_findings:
                key_findings = self._derive_key_findings(kb.analysis)

        # Fallback markdown if LLM did not provide full_markdown
        full_markdown = data.get("full_markdown", "")
        if not full_markdown:
            full_markdown = self._generate_fallback_markdown(data, kb)

        return ReportOutput(
            report_id=f"rep_{uuid.uuid4().hex[:8]}",
            created_at=datetime.now().isoformat(),
            title=data.get("title", "竞品分析报告"),
            executive_summary=data.get("executive_summary", ""),
            market_overview=data.get("market_overview", ""),
            product_positions=product_positions,
            key_findings=key_findings,
            swot_summary=swot_summary,
            gap_summary=gap_summary,
            strategic_recommendations=strategic_recommendations,
            risk_and_conflicts=data.get("risk_and_conflicts", ""),
            next_steps=data.get("next_steps", []),
            full_markdown=full_markdown,
        )

    def _derive_swot_summary(self, analysis: AnalysisReport) -> str:
        """Synthesize SWOT items into a concise summary."""
        categories = {
            "strength": "优势",
            "weakness": "劣势",
            "opportunity": "机会",
            "threat": "威胁",
        }
        groups: dict[str, list[str]] = {}
        for item in analysis.swot:
            groups.setdefault(item.category, []).append(item.content)
        if not groups:
            return ""
        lines = []
        for key, label in categories.items():
            if key in groups:
                lines.append(f"{label}：{'；'.join(groups[key])}")
        return "\n".join(lines)

    def _derive_gap_summary(self, analysis: AnalysisReport) -> str:
        """Synthesize gap items into a concise summary."""
        if not analysis.gaps:
            return ""
        lines = []
        for gap in analysis.gaps:
            impact = gap.impact or "medium"
            lines.append(f"- [{impact}] {gap.description}")
        return "\n".join(lines)

    def _derive_strategic_recommendations(
        self, analysis: AnalysisReport
    ) -> list[str]:
        """Derive strategic recommendations from analysis output."""
        return [
            f"{rec.title}：{rec.description}"
            for rec in analysis.recommendations
            if rec.title or rec.description
        ]

    def _derive_key_findings(self, analysis: AnalysisReport) -> list[KeyFinding]:
        """Fallback key findings derived from gaps and product scores."""
        findings: list[KeyFinding] = []
        for gap in analysis.gaps:
            findings.append(
                KeyFinding(
                    finding_id=f"f_{uuid.uuid4().hex[:6]}",
                    title=f"差距：{gap.description[:40]}",
                    detail=gap.description,
                    evidence=[gap.description],
                    related_product_ids=gap.compared_to_product_ids,
                    related_dimension_ids=[gap.dimension_id] if gap.dimension_id else [],
                )
            )
        for score in sorted(analysis.product_scores, key=lambda s: s.rank)[:3]:
            findings.append(
                KeyFinding(
                    finding_id=f"f_{uuid.uuid4().hex[:6]}",
                    title=f"评分排名：{score.product_name} 综合 #{score.rank}",
                    detail=f"总分 {score.total_score}，排名 #{score.rank}。",
                    evidence=[cs.rationale for cs in score.criterion_scores if cs.rationale],
                    related_product_ids=[score.product_id],
                    related_dimension_ids=[
                        cs.criterion_id for cs in score.criterion_scores
                    ],
                )
            )
        return findings

    def _generate_fallback_markdown(
        self, data: dict[str, Any], kb: KnowledgeBase
    ) -> str:
        """Generate a basic Markdown report if LLM fails to provide full_markdown."""
        lines: list[str] = []
        lines.append(f"# {data.get('title', '竞品分析报告')}")
        lines.append("")
        lines.append("## 执行摘要")
        lines.append(data.get("executive_summary", "暂无摘要。"))
        lines.append("")
        lines.append("## 市场概述")
        lines.append(data.get("market_overview", "暂无市场概述。"))
        lines.append("")

        if data.get("product_positions"):
            lines.append("## 产品定位")
            for pos in data["product_positions"]:
                lines.append(f"### {pos.get('product_name', '')}")
                lines.append(pos.get("positioning", ""))

        if data.get("strategic_recommendations"):
            lines.append("## 战略建议")
            for rec in data["strategic_recommendations"]:
                lines.append(f"- {rec}")

        return "\n".join(lines)
