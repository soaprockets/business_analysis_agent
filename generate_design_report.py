from docx import Document
from docx.shared import Pt, Inches, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_LINE_SPACING
from docx.oxml.ns import qn
from pathlib import Path

output_path = Path("output/project_design_report.docx")
output_path.parent.mkdir(parents=True, exist_ok=True)


def set_run_font(run, font_name="SimSun", size=10.5, bold=False):
    run.font.name = font_name
    run._element.rPr.rFonts.set(qn('w:eastAsia'), font_name)
    run.font.size = Pt(size)
    run.font.bold = bold


def add_heading_zh(doc, text, level=1):
    p = doc.add_heading(text, level=level)
    for run in p.runs:
        set_run_font(
            run,
            font_name="SimHei" if level <= 2 else "SimSun",
            size=(16 if level == 1 else (14 if level == 2 else 12)),
            bold=True,
        )
    return p


def add_paragraph_zh(doc, text, bold=False, first_line_indent=0.35, size=10.5):
    p = doc.add_paragraph()
    run = p.add_run(text)
    set_run_font(run, font_name="SimSun", size=size, bold=bold)
    p.paragraph_format.first_line_indent = Inches(first_line_indent)
    p.paragraph_format.line_spacing_rule = WD_LINE_SPACING.ONE_POINT_FIVE
    p.paragraph_format.space_after = Pt(6)
    return p


def add_bullets(doc, items):
    for item in items:
        p = doc.add_paragraph(style='List Bullet')
        run = p.add_run(item)
        set_run_font(run, font_name="SimSun", size=10.5)
        p.paragraph_format.line_spacing_rule = WD_LINE_SPACING.ONE_POINT_FIVE


doc = Document()

# Title
title = doc.add_heading('竞品专家多 Agent 系统设计方案说明', level=0)
title.alignment = WD_ALIGN_PARAGRAPH.CENTER
for run in title.runs:
    set_run_font(run, font_name="SimHei", size=22, bold=True)
doc.add_paragraph()

# Section 1
add_heading_zh(doc, '一、选题原因与真实问题', level=1)
add_paragraph_zh(doc,
    "在企业级软件、SaaS 以及消费电子等行业，竞品分析是产品规划和市场战略的核心输入。然而，传统的竞品分析工作大量依赖产品经理或市场研究员手工阅读 PDF、Word、网页、行业报告，然后在 Excel 或 PPT 中整理信息。这一过程存在以下真实痛点：")
add_bullets(doc, [
    "信息来源分散：竞品资料以多种格式（PDF、Word、HTML、Markdown、TXT）和多个渠道（内部文档、官网、第三方评测、社交媒体）存在，难以统一管理和检索。",
    "知识结构不统一：不同资料使用的描述维度各异，有的强调功能，有的强调定价，有的强调客户案例，人工整理时往往只能套用固定模板，导致大量有价值的信息被削足适履或遗漏。",
    "事实溯源困难：分析报告中的结论通常缺乏明确的来源标注，无法快速回答“这一结论来自哪份资料、哪一页、哪一段”，降低了报告的可信度和可审计性。",
    "网络信息未经验证：通过搜索引擎补充的信息（如价格、客户评价）可能与内部资料冲突，但现有工具缺乏自动反向验证机制，容易引入错误信息。",
    "分析过程不可复现：同一份资料由不同人员分析，结论可能差异很大；且从原始资料到最终报告的全过程缺乏可查看、可校验的中间产物。"
])
add_paragraph_zh(doc,
    "因此，本项目旨在构建一个从“任意可阅读竞品资料”到“结构化知识库”再到“可执行分析报告”的自动化、可解释、可验证的 Multi-Agent 系统，解决上述真实问题。")

# Section 2
add_heading_zh(doc, '二、解题思路与目标用户', level=1)
add_heading_zh(doc, '2.1 解题思路', level=2)
add_paragraph_zh(doc,
    "系统采用“多 Agent 分工 + 人在环路”的流水线架构，每个 Agent 负责一个专业能力边界清晰的任务，中间产物以结构化 JSON 持久化，最终输出机器可读的知识库与人类可读的 Markdown 报告。整体流程如下：")
add_bullets(doc, [
    "专家 Agent（ExpertAgent）：读取本地多格式文档，自动发现产品、动态维度、事实与来源引用；标记自有产品；记录信息冲突。",
    "搜索 Agent（SearchAgent）：通过 DuckDuckGo/Tavily 搜索竞品信息，抓取网页并提取结构化事实。",
    "反向验证（ExpertAgent 二次调用）：将搜索得到的事实与原始资料进行比对，确认、标记为外部补充或记录冲突，实现“搜索 → 验证 → 合并”的闭环。",
    "RAG 向量存储（RAGStore）：基于 Milvus Lite 对文档片段和事实建立向量索引，支持后续检索与验证。",
    "分析 Agent（AnalysisAgent）：对齐跨产品维度，构建对比矩阵；基于权重进行量化评分与排名；生成 SWOT、差距分析与可执行建议。",
    "报告专家 Agent（ReportAgent）：综合知识库与分析结果，生成面向决策者的最终报告（JSON + Markdown）。",
    "Agent 跟踪日志（AgentTraceLogger）：在每次调用时以 Markdown 形式展示各 Agent 的中间输出，证明每个阶段的工作效果。"
])
add_heading_zh(doc, '2.2 目标用户', level=2)
add_bullets(doc, [
    "产品经理：需要快速理解竞品功能、定价、定位，制定产品路线图。",
    "市场与竞争情报分析师：需要持续追踪多个竞品动态，生成可追溯的分析报告。",
    "战略规划人员：需要基于量化评分和 SWOT 进行战略决策。",
    "B2B SaaS / 企业软件公司的售前与解决方案团队：需要定制化的竞品对比材料。",
    "咨询公司与投资机构：需要对目标市场进行结构化研究和报告输出。"
])

# Section 3
add_heading_zh(doc, '三、与已有方案的设计对比', level=1)
add_paragraph_zh(doc, "下表从五个维度对比本方案与常见替代方案：")

table = doc.add_table(rows=1, cols=5)
table.style = 'Light Grid Accent 1'
hdr_cells = table.rows[0].cells
headers = ["对比维度", "手工 Excel/PPT", "通用 RAG 问答机器人", "单一大模型提示", "本方案"]
for i, h in enumerate(headers):
    run = hdr_cells[i].paragraphs[0].add_run(h)
    set_run_font(run, font_name="SimHei", size=10.5, bold=True)
    hdr_cells[i].paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER

rows = [
    ["维度定义", "固定模板，削足适履", "无结构化维度", "依赖 prompt 设计，维度不稳定", "动态发现，随资料自然演化"],
    ["事实溯源", "难以标注来源", "检索片段可参考，但不强制", "通常无来源", "每条事实强制 SourceRef（文档、页码/段落、引用）"],
    ["网络信息处理", "手工搜索、人工判断", "可检索网页，但无法验证", "易混入模型幻觉", "搜索 Agent 提取 + ExpertAgent 反向验证"],
    ["分析深度", "主观定性", "仅问答，无系统分析", "一次性生成，难以校验", "对比矩阵、量化评分、SWOT、差距、建议"],
    ["可解释性", "依赖个人经验", "黑盒检索", "黑盒生成", "Agent Trace 日志，逐阶段展示中间产物"],
    ["输出形态", "PPT/Excel", "对话文本", "长文本报告", "结构化 JSON + Markdown 报告双形态"],
]

for row_data in rows:
    row_cells = table.add_row().cells
    for i, text in enumerate(row_data):
        run = row_cells[i].paragraphs[0].add_run(text)
        set_run_font(run, font_name="SimSun", size=10)

add_paragraph_zh(doc,
    "相比已有方案，本方案的核心设计差异在于：将“知识抽取—搜索补充—反向验证—对比分析—报告生成”拆分为多个可独立迭代、可观测的 Agent，并用结构化数据模型（Pydantic）保证中间产物的质量与一致性；同时通过动态维度发现和事实溯源机制，兼顾了灵活性与可信度。")

# Section 4
add_heading_zh(doc, '四、最大困难与关键决策', level=1)
add_heading_zh(doc, '4.1 最大困难', level=2)
add_bullets(doc, [
    "大模型 JSON 输出不稳定：LLM 在生成长 JSON 时容易出现未转义引号、截断字符串、多余逗号等问题，导致后续解析失败。",
    "跨产品维度对齐困难：不同资料对同一概念使用不同术语（如“核心功能”vs“产品能力”vs“功能特性”），需要由模型进行语义聚类。",
    "搜索事实的可信度：网页信息可能与内部资料冲突，如何自动判断确认、外部补充或冲突是一大挑战。",
    "来源可追溯与信息压缩的平衡：既要保留每条事实的原始引用，又要避免报告被冗长引用淹没。",
    "长上下文与成本：完整资料、矩阵、评分一次性输入会占用大量 token，需要在 LLM 调用次数与上下文完整性之间取舍。"
])
add_heading_zh(doc, '4.2 关键决策', level=2)
add_bullets(doc, [
    "采用 Multi-Agent 而非单一大提示：降低单提示复杂度，使每个 Agent 专注于单一任务，便于调试、复用和迭代。",
    "数据模型先于提示：使用 Pydantic 定义 KnowledgeBase、FactItem、AnalysisReport、ReportOutput 等模型，强制中间产物结构化。",
    "动态维度优先于固定框架：不预设“定位/功能/定价”等固定维度，由 ExpertAgent 从资料中自然发现，再用 AnalysisAgent 对齐。",
    "事实状态机设计：为每条事实设置 confirmed / external_supplement / pending_verification / conflict 等状态，支持人在环路裁决。",
    "分析层与报告层分离：AnalysisAgent 负责结构化分析（矩阵、评分、SWOT、差距、建议），ReportAgent 负责叙事综合，避免重复提炼并保证一致性。",
    "引入 Agent Trace 日志：通过 Markdown 跟踪文件和控制台输出，让中间工作可被审计和验证。",
    "多 LLM Provider 兼容：同时支持 Anthropic、OpenAI 兼容接口以及火山方舟 Agent Plan，便于不同环境部署。"
])

add_paragraph_zh(doc, "以上设计决策共同支撑了一个高可解释、可迭代、可验证的竞品分析自动化系统。")

# Footer
doc.add_paragraph()
p = doc.add_paragraph()
p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
run = p.add_run("生成时间：2026-09-18")
set_run_font(run, font_name="SimSun", size=9)

doc.save(output_path)
print(f"已生成 Word 文档：{output_path.resolve()}")
