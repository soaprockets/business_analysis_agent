"""
Generate a human-readable Markdown report from a KnowledgeBase.
"""

from .models import (
    AnalysisReport,
    ComparisonMatrix,
    ConflictRecord,
    Dimension,
    FactItem,
    GapItem,
    KnowledgeBase,
    ProductProfile,
    ProductScore,
    RecommendationItem,
    SwotItem,
)


def generate_markdown_report(kb: KnowledgeBase) -> str:
    """Render a KnowledgeBase as a Markdown report."""
    lines: list[str] = []

    lines.append("# 竞品知识库报告")
    lines.append("")
    lines.append(f"**知识库 ID**：{kb.knowledge_base_id}")
    lines.append(f"**生成时间**：{kb.updated_at}")
    lines.append(f"**来源文档数**：{len(kb.source_documents)} 份")
    lines.append(f"**分析产品数**：{len(kb.analyzed_products)} 个")
    lines.append("")

    # 1. Source documents
    lines.append("## 一、来源文档清单")
    lines.append("")
    lines.append("| 文档 ID | 文件名 | 文件类型 | 处理时间 |")
    lines.append("|---|---|---|---|")
    for doc in kb.source_documents:
        lines.append(f"| {doc.doc_id} | {doc.file_name} | {doc.file_type} | {doc.uploaded_at} |")
    lines.append("")

    # 2. Product overview
    lines.append("## 二、产品总览")
    lines.append("")
    lines.append("| 产品名称 | 所属公司 | 一句话摘要 |")
    lines.append("|---|---|---|")
    for product in kb.products:
        summary_text = ""
        if product.summary:
            summary_text = product.summary.content[:80] + "..." if len(product.summary.content) > 80 else product.summary.content
        lines.append(f"| {product.product_name} | {product.company_name or '-'} | {summary_text} |")
    lines.append("")

    # 3. Detailed profiles
    lines.append("## 三、各产品详细画像")
    lines.append("")
    for idx, product in enumerate(kb.products, start=1):
        lines.extend(_render_product(product, idx))

    # 4. Conflicts
    if kb.conflicts_and_clarifications:
        lines.append("## 四、信息冲突与待人工裁决")
        lines.append("")
        lines.append("| 冲突 ID | 产品 | 维度 | 冲突内容 | 状态 |")
        lines.append("|---|---|---|---|---|")
        for conflict in kb.conflicts_and_clarifications:
            lines.extend(_render_conflict(conflict))
        lines.append("")

    # 5. Competitive analysis
    if kb.analysis:
        lines.extend(_render_analysis(kb))

    return "\n".join(lines)


def _render_product(product: ProductProfile, index: int) -> list[str]:
    lines: list[str] = []
    lines.append(f"### 3.{index} {product.product_name}")
    lines.append("")
    lines.append(f"- **所属公司**：{product.company_name or '未提及'}")
    lines.append(f"- **产品 ID**：{product.product_id}")
    lines.append("")

    if product.summary:
        lines.append("#### 综合摘要")
        lines.append("")
        lines.append(product.summary.content)
        lines.append("")
        lines.append(_render_source_refs(product.summary.source_refs))
        lines.append("")

    if not product.dimensions:
        lines.append("*该文档中未提取到具体维度。*")
        lines.append("")
        return lines

    for dim in product.dimensions:
        lines.extend(_render_dimension(dim))

    return lines


def _render_dimension(dim: Dimension) -> list[str]:
    lines: list[str] = []
    lines.append(f"#### {dim.dimension_name}")
    lines.append("")

    for item in dim.items:
        lines.append(f"- {item.content}")
        lines.append(f"  - 状态：{item.status} | 置信度：{item.confidence}")
        if item.note:
            lines.append(f"  - 备注：{item.note}")
        lines.append(f"  - {_render_source_refs_inline(item.source_refs)}")
    lines.append("")

    return lines


def _render_source_refs(source_refs: list) -> str:
    if not source_refs:
        return "*无来源标注*"
    parts = []
    for ref in source_refs:
        loc = f"，{ref.page_or_section}" if ref.page_or_section else ""
        quote = f"：\"{ref.quote}\"" if ref.quote else ""
        parts.append(f"- 来源：{ref.file_name}{loc}{quote}")
    return "\n".join(parts)


def _render_source_refs_inline(source_refs: list) -> str:
    if not source_refs:
        return "来源：无"
    parts = []
    for ref in source_refs:
        loc = f" {ref.page_or_section}" if ref.page_or_section else ""
        parts.append(f"{ref.file_name}{loc}")
    return "来源：" + "；".join(parts)


def _render_conflict(conflict: ConflictRecord) -> list[str]:
    lines: list[str] = []
    content_summary = " / ".join(
        f"{item.content[:60]}..." if len(item.content) > 60 else item.content
        for item in conflict.conflicting_items
    )
    status = "已裁决" if conflict.resolution else "待裁决"
    lines.append(
        f"| {conflict.conflict_id} | {conflict.product_id} | {conflict.dimension} | {content_summary} | {status} |"
    )
    return lines


def _render_analysis(kb: KnowledgeBase) -> list[str]:
    """Render the competitive analysis section."""
    analysis = kb.analysis
    if analysis is None:
        return []

    lines: list[str] = []
    lines.append("## 五、竞争分析")
    lines.append("")
    lines.append(f"**分析 ID**：{analysis.report_id}")
    lines.append(f"**生成时间**：{analysis.created_at}")

    own_product_name = "未标记"
    if analysis.own_product_id:
        own = next(
            (p for p in kb.products if p.product_id == analysis.own_product_id),
            None,
        )
        own_product_name = own.product_name if own else analysis.own_product_id
    lines.append(f"**自有产品**：{own_product_name}")
    lines.append("")

    lines.extend(_render_comparison_matrix(analysis.comparison_matrix, kb))
    lines.extend(_render_scores(analysis.product_scores, kb))
    lines.extend(_render_swot(analysis.swot))
    lines.extend(_render_gaps(analysis.gaps))
    lines.extend(_render_recommendations(analysis.recommendations))

    return lines


def _render_comparison_matrix(matrix: ComparisonMatrix, kb: KnowledgeBase) -> list[str]:
    """Render the comparison matrix as a markdown table."""
    lines: list[str] = []
    lines.append("### 5.1 对比矩阵")
    lines.append("")

    product_map = {p.product_id: p for p in kb.products}
    product_ids = [pid for pid in matrix.product_ids if pid in product_map]
    product_names = [product_map[pid].product_name for pid in product_ids]

    if not matrix.dimensions or not product_ids:
        lines.append("*无足够数据生成对比矩阵。*")
        lines.append("")
        return lines

    header = "| 维度 | " + " | ".join(product_names) + " |"
    separator = "|---" * (len(product_names) + 1) + "|"
    lines.append(header)
    lines.append(separator)

    cells_by_dim: dict[str, dict[str, str]] = {
        dim.dimension_id: {pid: "" for pid in product_ids}
        for dim in matrix.dimensions
    }
    for cell in matrix.cells:
        if cell.dimension_id in cells_by_dim and cell.product_id in product_ids:
            text = cell.summary.replace("|", "\\|")
            if len(text) > 120:
                text = text[:117] + "..."
            cells_by_dim[cell.dimension_id][cell.product_id] = text

    for dim in matrix.dimensions:
        row = f"| {dim.dimension_name} |"
        for pid in product_ids:
            row += f" {cells_by_dim[dim.dimension_id].get(pid, '')} |"
        lines.append(row)

    lines.append("")
    return lines


def _render_scores(scores: list[ProductScore], kb: KnowledgeBase) -> list[str]:
    """Render quantitative scores and rankings."""
    lines: list[str] = []
    lines.append("### 5.2 量化评分与排名")
    lines.append("")

    if not scores:
        lines.append("*暂无评分数据。*")
        lines.append("")
        return lines

    product_map = {p.product_id: p for p in kb.products}
    criterion_ids: list[str] = []
    if scores:
        criterion_ids = [cs.criterion_id for cs in scores[0].criterion_scores]

    header = "| 排名 | 产品 | 总分 | " + " | ".join(criterion_ids) + " |"
    separator = "|---|---|---" + "|---" * len(criterion_ids) + "|"
    lines.append(header)
    lines.append(separator)

    for score in sorted(scores, key=lambda s: s.rank):
        product_name = product_map.get(score.product_id, score).product_name
        row = f"| #{score.rank} | {product_name} | {score.total_score} |"
        for cid in criterion_ids:
            cs = next((c for c in score.criterion_scores if c.criterion_id == cid), None)
            row += f" {cs.score if cs else '-'} |"
        lines.append(row)

    lines.append("")
    return lines


def _render_swot(swot: list[SwotItem]) -> list[str]:
    """Render SWOT analysis."""
    lines: list[str] = []
    lines.append("### 5.3 SWOT 分析")
    lines.append("")

    if not swot:
        lines.append("*暂无 SWOT 分析。*")
        lines.append("")
        return lines

    categories = {
        "strength": "优势 (Strengths)",
        "weakness": "劣势 (Weaknesses)",
        "opportunity": "机会 (Opportunities)",
        "threat": "威胁 (Threats)",
    }

    grouped: dict[str, list[SwotItem]] = {key: [] for key in categories}
    for item in swot:
        grouped.setdefault(item.category, []).append(item)

    for key, label in categories.items():
        lines.append(f"#### {label}")
        lines.append("")
        items = grouped.get(key, [])
        if not items:
            lines.append("*暂无。*")
        else:
            for item in items:
                lines.append(f"- {item.content}")
        lines.append("")

    return lines


def _render_gaps(gaps: list[GapItem]) -> list[str]:
    """Render gap analysis."""
    lines: list[str] = []
    lines.append("### 5.4 差距分析")
    lines.append("")

    if not gaps:
        lines.append("*暂无差距分析。*")
        lines.append("")
        return lines

    lines.append("| 差距 | 影响 | 对比竞品 |")
    lines.append("|---|---|---|")
    for gap in gaps:
        desc = gap.description.replace("|", "\\|")
        competitors = ", ".join(gap.compared_to_product_ids) or "-"
        lines.append(f"| {desc} | {gap.impact} | {competitors} |")
    lines.append("")

    return lines


def _render_recommendations(recommendations: list[RecommendationItem]) -> list[str]:
    """Render prioritized recommendations."""
    lines: list[str] = []
    lines.append("### 5.5 行动建议")
    lines.append("")

    if not recommendations:
        lines.append("*暂无建议。*")
        lines.append("")
        return lines

    priority_order = {"high": 0, "medium": 1, "low": 2}
    sorted_recs = sorted(
        recommendations,
        key=lambda r: priority_order.get(r.priority, 99),
    )

    for idx, rec in enumerate(sorted_recs, start=1):
        badge = {"high": "🔴 高", "medium": "🟡 中", "low": "🟢 低"}.get(
            rec.priority, rec.priority
        )
        lines.append(f"{idx}. **[{badge}] {rec.title}**")
        lines.append(f"   - 内容：{rec.description}")
        lines.append(f"   - 依据：{rec.rationale}")
        if rec.expected_impact:
            lines.append(f"   - 预期效果：{rec.expected_impact}")
        lines.append("")

    return lines
