"""
Trace logger that records intermediate outputs from each agent as Markdown.

This is useful for proving that each stage of the pipeline produced meaningful
work: ExpertAgent extracted products and facts, SearchAgent discovered web facts,
AnalysisAgent built a matrix/scores/SWOT/gaps/recommendations, and ReportAgent
synthesized a final report.
"""

from datetime import datetime
from pathlib import Path
from typing import Any

from .models import AnalysisReport, KnowledgeBase, ReportOutput, SearchResult


class AgentTraceLogger:
    """Logs per-agent intermediate outputs to a Markdown trace file."""

    def __init__(
        self,
        output_dir: str | Path,
        kb_id: str,
        enabled: bool = True,
        console: bool = True,
    ):
        self.enabled = enabled
        self.console = console
        self.path = Path(output_dir) / f"{kb_id}_trace.md"
        if self.enabled:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._write_header()

    def _write_header(self) -> None:
        timestamp = datetime.now().isoformat()
        if self.path.exists():
            header = [
                "",
                f"## 新的跟踪记录  {timestamp}",
                "",
            ]
            mode = "a"
        else:
            header = [
                f"# Agent 执行过程跟踪报告",
                "",
                f"**知识库 ID**：{self.path.stem.replace('_trace', '')}",
                f"**首次生成时间**：{timestamp}",
                "",
                "> 本文件记录每个 Agent 的中间输出，用于验证 pipeline 各阶段的工作效果。",
                "",
            ]
            mode = "w"
        with open(self.path, mode, encoding="utf-8") as f:
            f.write("\n".join(header) + "\n")

    def _emit(self, title: str, body_lines: list[str]) -> None:
        if not self.enabled:
            return
        timestamp = datetime.now().isoformat(timespec="seconds")
        section = [f"## {title}", f"*{timestamp}*", ""] + body_lines + [""]
        with open(self.path, "a", encoding="utf-8") as f:
            f.write("\n".join(section) + "\n")
        if self.console:
            print(f"\n{'=' * 60}")
            print(f"## {title}")
            for line in body_lines[:50]:
                print(line)
            if len(body_lines) > 50:
                print(f"... （还有 {len(body_lines) - 50} 行，详见 {self.path}）")
            print("=" * 60)

    def log_build(self, kb: KnowledgeBase, documents: list[Any] | None = None) -> None:
        """Log ExpertAgent extraction results."""
        if documents is None:
            documents = list(kb.source_documents)
        lines: list[str] = []
        lines.append(f"### 来源文档（{len(documents)} 份）")
        lines.append("")
        for doc in documents:
            file_name = getattr(doc, "file_name", getattr(doc, "title", str(doc)))
            text_len = len(getattr(doc, "text", ""))
            if text_len:
                lines.append(f"- `{file_name}`：{text_len} 字符")
            else:
                lines.append(f"- `{file_name}`")
        lines.append("")

        lines.append(f"### 识别到的产品（{len(kb.products)} 个）")
        lines.append("")
        lines.append("| 产品 | 公司 | 自有产品 | 维度数 | 事实数 |")
        lines.append("|---|---|---|---|---|")
        total_facts = 0
        for product in kb.products:
            fact_count = sum(len(dim.items) for dim in product.dimensions)
            total_facts += fact_count
            own = "是" if product.is_own_product else "否"
            lines.append(
                f"| {product.product_name} | {product.company_name or '-'} | {own} | "
                f"{len(product.dimensions)} | {fact_count} |"
            )
        lines.append("")

        # Show representative facts per product
        for product in kb.products:
            lines.append(f"#### {product.product_name} 关键事实")
            lines.append("")
            facts = [
                item
                for dim in product.dimensions
                for item in dim.items
            ]
            for idx, item in enumerate(facts[:5], start=1):
                lines.append(
                    f"{idx}. [{item.status}/{item.confidence}] {item.content}"
                )
            if len(facts) > 5:
                lines.append(f"   ... 还有 {len(facts) - 5} 条事实")
            lines.append("")

        lines.append(f"### 自有产品")
        lines.append("")
        own = next(
            (p for p in kb.products if p.product_id == kb.own_product_id), None
        )
        if own:
            lines.append(f"- **{own.product_name}**（ID: `{kb.own_product_id}`）")
        else:
            lines.append("- 未标记")
        lines.append("")

        lines.append(f"### 冲突与待裁决")
        lines.append("")
        if kb.conflicts_and_clarifications:
            lines.append(f"- 共 {len(kb.conflicts_and_clarifications)} 条冲突")
        else:
            lines.append("- 无")
        lines.append("")

        self._emit("1. ExpertAgent：知识抽取", lines)

    def log_search(self, search_results: list[SearchResult]) -> None:
        """Log SearchAgent web search results."""
        lines: list[str] = []
        total_facts = sum(len(r.extracted_facts) for r in search_results)
        lines.append(f"### 搜索结果摘要（{len(search_results)} 个页面，共 {total_facts} 条事实）")
        lines.append("")
        for idx, result in enumerate(search_results, start=1):
            lines.append(f"#### [{idx}] {result.title}")
            lines.append(f"- URL：{result.url}")
            lines.append(f"- 查询：{result.query}")
            lines.append(f"- 提取事实数：{len(result.extracted_facts)}")
            for f_idx, fact in enumerate(result.extracted_facts[:5], start=1):
                lines.append(
                    f"  {f_idx}. [{fact.confidence}] {fact.content}"
                )
            if len(result.extracted_facts) > 5:
                lines.append(
                    f"  ... 还有 {len(result.extracted_facts) - 5} 条事实"
                )
            lines.append("")
        self._emit("2. SearchAgent：网页搜索", lines)

    def log_supplement(self, kb: KnowledgeBase) -> None:
        """Log facts after ExpertAgent verifies search results."""
        lines: list[str] = []
        status_counts: dict[str, int] = {}
        product_fact_counts: dict[str, int] = {}
        for product in kb.products:
            count = 0
            for dim in product.dimensions:
                for item in dim.items:
                    count += 1
                    status_counts[item.status] = status_counts.get(item.status, 0) + 1
            product_fact_counts[product.product_name] = count

        lines.append("### 补充后各产品事实数")
        lines.append("")
        lines.append("| 产品 | 事实总数 |")
        lines.append("|---|---|")
        for name, count in product_fact_counts.items():
            lines.append(f"| {name} | {count} |")
        lines.append("")

        lines.append("### 事实状态分布")
        lines.append("")
        if status_counts:
            for status, count in sorted(status_counts.items()):
                lines.append(f"- `{status}`：{count}")
        else:
            lines.append("- 无")
        lines.append("")
        self._emit("3. ExpertAgent：搜索事实验证与合并", lines)

    def log_analysis(self, analysis: AnalysisReport, kb: KnowledgeBase) -> None:
        """Log AnalysisAgent structured analysis."""
        lines: list[str] = []
        product_map = {p.product_id: p for p in kb.products}

        own = product_map.get(analysis.own_product_id or "")
        lines.append(f"### 自有产品：{own.product_name if own else '未标记'}")
        lines.append("")

        # Comparison matrix
        lines.append(f"### 对比矩阵（{len(analysis.comparison_matrix.dimensions)} 维度）")
        lines.append("")
        product_ids = analysis.comparison_matrix.product_ids
        product_names = [
            product_map.get(pid, type("P", (), {"product_name": pid})()).product_name
            for pid in product_ids
        ]
        lines.append("| 维度 | " + " | ".join(product_names) + " |")
        lines.append("|---" + "|---" * len(product_names) + "|")
        cells_by_dim: dict[str, dict[str, str]] = {
            dim.dimension_id: {pid: "" for pid in product_ids}
            for dim in analysis.comparison_matrix.dimensions
        }
        for cell in analysis.comparison_matrix.cells:
            if cell.dimension_id in cells_by_dim and cell.product_id in product_ids:
                cells_by_dim[cell.dimension_id][cell.product_id] = cell.summary
        for dim in analysis.comparison_matrix.dimensions:
            row = f"| {dim.dimension_name} |"
            for pid in product_ids:
                text = cells_by_dim[dim.dimension_id].get(pid, "-")
                row += f" {text.replace('|', '｜')} |"
            lines.append(row)
        lines.append("")

        # Scores
        lines.append("### 量化评分与排名")
        lines.append("")
        lines.append("| 排名 | 产品 | 总分 |")
        lines.append("|---|---|---|")
        for score in sorted(analysis.product_scores, key=lambda s: s.rank):
            name = product_map.get(score.product_id, score).product_name
            lines.append(f"| #{score.rank} | {name} | {score.total_score} |")
        lines.append("")

        # SWOT
        lines.append("### SWOT 分析")
        lines.append("")
        categories = {
            "strength": "优势",
            "weakness": "劣势",
            "opportunity": "机会",
            "threat": "威胁",
        }
        for key, label in categories.items():
            items = [i for i in analysis.swot if i.category == key]
            lines.append(f"#### {label}")
            if not items:
                lines.append("- 无")
            for item in items:
                lines.append(f"- {item.content}")
            lines.append("")

        # Gaps
        lines.append("### 差距分析")
        lines.append("")
        if analysis.gaps:
            lines.append("| 差距 | 影响 | 对比竞品 |")
            lines.append("|---|---|---|")
            for gap in analysis.gaps:
                competitors = ", ".join(gap.compared_to_product_ids) or "-"
                desc = gap.description.replace("|", "｜")
                lines.append(f"| {desc} | {gap.impact} | {competitors} |")
        else:
            lines.append("- 无")
        lines.append("")

        # Recommendations
        lines.append("### 行动建议")
        lines.append("")
        if analysis.recommendations:
            priority_order = {"high": 0, "medium": 1, "low": 2}
            recs = sorted(
                analysis.recommendations,
                key=lambda r: priority_order.get(r.priority, 99),
            )
            for idx, rec in enumerate(recs, start=1):
                lines.append(
                    f"{idx}. **[{rec.priority}] {rec.title}** — {rec.description}"
                )
                lines.append(f"   - 依据：{rec.rationale}")
        else:
            lines.append("- 无")
        lines.append("")

        self._emit("4. AnalysisAgent：竞争分析", lines)

    def log_report(self, report: ReportOutput) -> None:
        """Log ReportAgent final synthesis."""
        lines: list[str] = []
        lines.append(f"### 报告标题：{report.title}")
        lines.append("")
        lines.append("### 执行摘要")
        lines.append(report.executive_summary or "-")
        lines.append("")
        lines.append("### 市场概述")
        lines.append(report.market_overview or "-")
        lines.append("")

        lines.append("### 产品定位")
        lines.append("")
        for pos in report.product_positions:
            lines.append(f"#### {pos.product_name}")
            lines.append(f"- 定位：{pos.positioning}")
            lines.append(f"- 优势：{', '.join(pos.key_strengths) or '-'}")
            lines.append(f"- 劣势：{', '.join(pos.key_weaknesses) or '-'}")
            lines.append("")

        lines.append("### 关键发现")
        lines.append("")
        if report.key_findings:
            for idx, finding in enumerate(report.key_findings, start=1):
                lines.append(f"{idx}. **{finding.title}** — {finding.detail}")
        else:
            lines.append("- 无")
        lines.append("")

        lines.append("### 战略建议")
        lines.append("")
        if report.strategic_recommendations:
            for idx, rec in enumerate(report.strategic_recommendations, start=1):
                lines.append(f"{idx}. {rec}")
        else:
            lines.append("- 无")
        lines.append("")

        lines.append("### 下一步行动")
        lines.append("")
        if report.next_steps:
            for idx, step in enumerate(report.next_steps, start=1):
                lines.append(f"{idx}. {step}")
        else:
            lines.append("- 无")
        lines.append("")

        self._emit("5. ReportAgent：最终报告", lines)

    def finish(self) -> None:
        if not self.enabled:
            return
        tail = [
            "---",
            "",
            f"**跟踪报告保存位置**：`{self.path}`",
            "",
        ]
        with open(self.path, "a", encoding="utf-8") as f:
            f.write("\n".join(tail) + "\n")
        if self.console:
            print(f"\n📋 Agent 跟踪报告已保存：{self.path}")
