"""
CLI entry point for the competitive product expert agent.

Commands:
    build   Build a knowledge base from local documents.
    search  Search the web for a product and supplement an existing KB.
"""

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

from .analysis_agent import AnalysisAgent
from .expert_agent import ExpertAgent
from .models import KnowledgeBase, ReportOutput, ScoreCriterion
from .parser import parse_documents
from .report_agent import ReportAgent
from .report_generator import generate_markdown_report
from .search_agent import SearchAgent
from .trace_logger import AgentTraceLogger

load_dotenv()


def check_api_key():
    provider = os.getenv("LLM_PROVIDER", "anthropic").lower()
    if provider == "anthropic":
        if not os.getenv("ANTHROPIC_API_KEY"):
            print("错误：未设置 ANTHROPIC_API_KEY 环境变量。", file=sys.stderr)
            print("请先复制 .env.example 为 .env 并填入 API Key。", file=sys.stderr)
            sys.exit(1)
    elif provider == "openai":
        if not (os.getenv("OPENAI_API_KEY") or os.getenv("DOUBAO_API_KEY")):
            print("错误：LLM_PROVIDER=openai 时，需要设置 OPENAI_API_KEY 或 DOUBAO_API_KEY 环境变量。", file=sys.stderr)
            print("请先复制 .env.example 为 .env 并填入 API Key。", file=sys.stderr)
            sys.exit(1)
    elif provider == "volcano-agent-plan":
        if not (
            os.getenv("VOLCANO_AGENT_API_KEY")
            or os.getenv("OPENAI_API_KEY")
            or os.getenv("DOUBAO_API_KEY")
        ):
            print(
                "错误：LLM_PROVIDER=volcano-agent-plan 时，需要设置 VOLCANO_AGENT_API_KEY "
                "（或 OPENAI_API_KEY / DOUBAO_API_KEY）环境变量。",
                file=sys.stderr,
            )
            print("请先复制 .env.example 为 .env 并填入 API Key。", file=sys.stderr)
            sys.exit(1)
    else:
        print(f"错误：不支持的 LLM_PROVIDER: {provider}", file=sys.stderr)
        sys.exit(1)


def save_kb(kb: KnowledgeBase, output_dir: Path):
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / f"{kb.knowledge_base_id}.json"
    md_path = output_dir / f"{kb.knowledge_base_id}.md"

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(kb.to_dict(), f, ensure_ascii=False, indent=2)

    report = generate_markdown_report(kb)
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(report)

    return json_path, md_path


def save_report(report: ReportOutput, kb_id: str, output_dir: Path):
    """Save the final structured report to JSON and Markdown files."""
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / f"{kb_id}_report.json"
    md_path = output_dir / f"{kb_id}_report.md"

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(report.model_dump(mode="json", exclude_none=True), f, ensure_ascii=False, indent=2)

    with open(md_path, "w", encoding="utf-8") as f:
        f.write(report.full_markdown)

    return json_path, md_path


def cmd_build(args):
    check_api_key()

    missing = [f for f in args.files if not Path(f).exists()]
    if missing:
        print(f"错误：以下文件不存在：{', '.join(missing)}", file=sys.stderr)
        sys.exit(1)

    print(f"正在解析 {len(args.files)} 个文件...")
    documents = parse_documents(args.files)
    for doc in documents:
        print(f"  ✓ {doc.file_name}: {len(doc.text)} 字符")

    print("\n正在调用专家 Agent 提取知识...")
    agent = ExpertAgent(model=args.model)
    kb = agent.build_knowledge_base(
        documents, kb_id=args.kb_id, own_product_name=args.own_product
    )

    output_dir = Path(args.output_dir)
    trace = AgentTraceLogger(output_dir, kb.knowledge_base_id, enabled=args.trace)
    trace.log_build(kb, documents)

    json_path, md_path = save_kb(kb, output_dir)
    trace.finish()

    print(f"\n✅ 知识库已生成")
    print(f"   JSON: {json_path}")
    print(f"   报告: {md_path}")
    print(f"   产品: {', '.join(kb.analyzed_products) or '无'}")
    print(f"   自有产品: {kb.own_product_id or '未标记'}")
    print(f"   维度总数: {sum(len(p.dimensions) for p in kb.products)}")


def cmd_search(args):
    check_api_key()

    kb_path = Path(args.kb_file)
    if not kb_path.exists():
        print(f"错误：知识库文件不存在：{args.kb_file}", file=sys.stderr)
        sys.exit(1)

    print(f"正在加载知识库: {kb_path}")
    with open(kb_path, "r", encoding="utf-8") as f:
        kb = KnowledgeBase(**json.load(f))

    # Reload original documents referenced by the KB
    source_files = [sd.file_name for sd in kb.source_documents]
    existing = {str(p) for p in Path(args.doc_dir).glob("*") if p.is_file()}
    available = [f for f in source_files if f in existing or (Path(args.doc_dir) / f).exists()]

    if not available:
        print(
            f"错误：找不到原始资料文件。请把原始资料放在 {args.doc_dir} 目录下。",
            file=sys.stderr,
        )
        sys.exit(1)

    documents = parse_documents([Path(args.doc_dir) / f for f in available])

    output_dir = Path(args.output_dir)
    trace = AgentTraceLogger(output_dir, kb.knowledge_base_id, enabled=args.trace)
    trace.log_build(kb, documents)

    print(f"\n正在搜索: {args.query}")
    search_agent = SearchAgent(
        model=args.model,
        max_results=args.max_results,
        backend=args.search_backend,
    )
    results = search_agent.search(
        query=args.query,
        product_name=args.product_name,
        context=args.context,
    )

    total_facts = sum(len(r.extracted_facts) for r in results)
    print(f"\n   共提取 {total_facts} 条网络事实")
    trace.log_search(results)

    expert_agent = ExpertAgent(model=args.model)
    kb = expert_agent.supplement_with_search_results(kb, results, documents)
    trace.log_supplement(kb)

    json_path, md_path = save_kb(kb, output_dir)
    trace.finish()

    print(f"\n✅ 知识库已更新")
    print(f"   JSON: {json_path}")
    print(f"   报告: {md_path}")
    print(f"   产品: {', '.join(kb.analyzed_products) or '无'}")
    print(f"   维度总数: {sum(len(p.dimensions) for p in kb.products)}")
    print(f"   待裁决冲突: {len(kb.conflicts_and_clarifications)}")


def cmd_analyze(args):
    check_api_key()

    kb_path = Path(args.kb_file)
    if not kb_path.exists():
        print(f"错误：知识库文件不存在：{args.kb_file}", file=sys.stderr)
        sys.exit(1)

    print(f"正在加载知识库: {kb_path}")
    with open(kb_path, "r", encoding="utf-8") as f:
        kb = KnowledgeBase(**json.load(f))

    criteria = None
    if args.criteria_file:
        crit_path = Path(args.criteria_file)
        if not crit_path.exists():
            print(f"错误：评分标准文件不存在：{args.criteria_file}", file=sys.stderr)
            sys.exit(1)
        with open(crit_path, "r", encoding="utf-8") as f:
            raw_criteria = json.load(f)
        criteria = [ScoreCriterion(**c) for c in raw_criteria]

    output_dir = Path(args.output_dir)
    trace = AgentTraceLogger(output_dir, kb.knowledge_base_id, enabled=args.trace)
    trace.log_build(kb)

    print("\n正在调用分析 Agent 生成竞争分析报告...")
    agent = AnalysisAgent(model=args.model, criteria=criteria)
    report = agent.analyze(kb)

    kb.analysis = report
    kb.updated_at = datetime.now().isoformat()
    trace.log_analysis(report, kb)

    final_report = None
    if args.generate_report:
        print("\n正在调用报告专家 Agent 生成最终报告...")
        report_agent = ReportAgent(model=args.model)
        final_report = report_agent.generate_report(kb)
        kb.report = final_report
        kb.updated_at = datetime.now().isoformat()
        trace.log_report(final_report)

    json_path, md_path = save_kb(kb, output_dir)
    trace.finish()

    print(f"\n✅ 分析报告已生成")
    print(f"   JSON: {json_path}")
    print(f"   报告: {md_path}")
    print(f"   自有产品: {report.own_product_id or '未标记'}")
    print(f"   评分排名: ", end="")
    for score in report.product_scores:
        print(f"#{score.rank} {score.product_name}({score.total_score}) ", end="")
    print()
    print(f"   建议数: {len(report.recommendations)}")

    if final_report:
        report_json_path, report_md_path = save_report(
            final_report, kb.knowledge_base_id, output_dir
        )
        print(f"\n✅ 最终报告已生成")
        print(f"   报告 JSON: {report_json_path}")
        print(f"   报告 Markdown: {report_md_path}")


def cmd_report(args):
    check_api_key()

    kb_path = Path(args.kb_file)
    if not kb_path.exists():
        print(f"错误：知识库文件不存在：{args.kb_file}", file=sys.stderr)
        sys.exit(1)

    print(f"正在加载知识库: {kb_path}")
    with open(kb_path, "r", encoding="utf-8") as f:
        kb = KnowledgeBase(**json.load(f))

    output_dir = Path(args.output_dir)
    trace = AgentTraceLogger(output_dir, kb.knowledge_base_id, enabled=args.trace)
    trace.log_build(kb)

    if not kb.analysis:
        print("警告：该知识库尚未运行分析，报告将仅基于原始知识库生成。", file=sys.stderr)

    print("\n正在调用报告专家 Agent 生成最终报告...")
    agent = ReportAgent(model=args.model)
    final_report = agent.generate_report(kb)

    kb.report = final_report
    kb.updated_at = datetime.now().isoformat()
    trace.log_report(final_report)

    report_json_path, report_md_path = save_report(
        final_report, kb.knowledge_base_id, output_dir
    )

    # Save updated KB JSON with report reference only (avoid regenerating KB markdown)
    kb_json_path = output_dir / f"{kb.knowledge_base_id}.json"
    with open(kb_json_path, "w", encoding="utf-8") as f:
        json.dump(kb.to_dict(), f, ensure_ascii=False, indent=2)

    print(f"\n✅ 最终报告已生成")
    print(f"   报告 JSON: {report_json_path}")
    print(f"   报告 Markdown: {report_md_path}")


def main():
    parser = argparse.ArgumentParser(
        description="竞品知识库构建与搜索补充工具"
    )
    parser.add_argument(
        "--model",
        default=None,
        help="覆盖默认的 Anthropic 模型",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # build command
    build_parser = subparsers.add_parser("build", help="从本地文档构建知识库")
    build_parser.add_argument(
        "files",
        nargs="+",
        help="一个或多个竞品资料文件路径（支持 PDF、Word、HTML、Markdown、TXT 等）",
    )
    build_parser.add_argument(
        "--output-dir",
        "-o",
        default="output",
        help="输出目录，默认 output/",
    )
    build_parser.add_argument(
        "--kb-id",
        default=None,
        help="知识库 ID，默认自动生成",
    )
    build_parser.add_argument(
        "--own-product",
        default=None,
        help="标记我们自己的产品名称（用于后续竞品对比分析）",
    )
    build_parser.add_argument(
        "--trace",
        action="store_true",
        help="启用 Agent 中间输出 Markdown 跟踪，输出到 {kb_id}_trace.md",
    )
    build_parser.set_defaults(func=cmd_build)

    # search command
    search_parser = subparsers.add_parser(
        "search", help="搜索网页并把结果补充进现有知识库"
    )
    search_parser.add_argument(
        "kb_file",
        help="现有知识库 JSON 文件路径",
    )
    search_parser.add_argument(
        "product_name",
        help="要搜索的竞品名称",
    )
    search_parser.add_argument(
        "query",
        help="搜索关键词",
    )
    search_parser.add_argument(
        "--doc-dir",
        default="examples",
        help="原始资料所在目录，默认 examples/",
    )
    search_parser.add_argument(
        "--context",
        default=None,
        help="给搜索 Agent 的额外背景信息",
    )
    search_parser.add_argument(
        "--max-results",
        type=int,
        default=3,
        help="最多搜索并处理的结果数，默认 3",
    )
    search_parser.add_argument(
        "--output-dir",
        "-o",
        default="output",
        help="输出目录，默认 output/",
    )
    search_parser.add_argument(
        "--search-backend",
        default="duckduckgo",
        choices=["duckduckgo", "tavily", "mock"],
        help="搜索引擎后端，默认 duckduckgo（可选 tavily/mock）",
    )
    search_parser.add_argument(
        "--trace",
        action="store_true",
        help="启用 Agent 中间输出 Markdown 跟踪，输出到 {kb_id}_trace.md",
    )
    search_parser.set_defaults(func=cmd_search)

    # analyze command
    analyze_parser = subparsers.add_parser(
        "analyze", help="对已有知识库进行竞品对比分析"
    )
    analyze_parser.add_argument(
        "kb_file",
        help="现有知识库 JSON 文件路径",
    )
    analyze_parser.add_argument(
        "--output-dir",
        "-o",
        default="output",
        help="输出目录，默认 output/",
    )
    analyze_parser.add_argument(
        "--criteria-file",
        default=None,
        help="可选的 JSON 文件，覆盖默认评分维度与权重",
    )
    analyze_parser.add_argument(
        "--generate-report",
        action="store_true",
        help="分析完成后调用报告专家 Agent 生成最终报告",
    )
    analyze_parser.add_argument(
        "--trace",
        action="store_true",
        help="启用 Agent 中间输出 Markdown 跟踪，输出到 {kb_id}_trace.md",
    )
    analyze_parser.set_defaults(func=cmd_analyze)

    # report command
    report_parser = subparsers.add_parser(
        "report", help="基于知识库生成结构化竞品分析报告"
    )
    report_parser.add_argument(
        "kb_file",
        help="现有知识库 JSON 文件路径",
    )
    report_parser.add_argument(
        "--output-dir",
        "-o",
        default="output",
        help="输出目录，默认 output/",
    )
    report_parser.add_argument(
        "--trace",
        action="store_true",
        help="启用 Agent 中间输出 Markdown 跟踪，输出到 {kb_id}_trace.md",
    )
    report_parser.set_defaults(func=cmd_report)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
