from fpdf import FPDF
from pathlib import Path

output_path = Path("output/project_design_presentation.pdf")
output_path.parent.mkdir(parents=True, exist_ok=True)

font_path = "/Library/Fonts/Arial Unicode.ttf"

slides = [
    {
        "title": "竞品专家多 Agent 系统",
        "subtitle": "设计思路与关键决策",
        "bullets": [],
    },
    {
        "title": "一、为什么要做这个项目",
        "bullets": [
            "竞品分析是产品规划和市场战略的核心输入",
            "传统方式依赖人工阅读 PDF / Word / 网页 / 行业报告",
            "信息来源分散、维度不统一、结论难以溯源",
            "网络信息未经验证，容易引入错误",
            "需要自动化、可解释、可验证的竞品分析系统",
        ],
    },
    {
        "title": "真实痛点",
        "bullets": [
            "来源分散：PDF、Word、HTML、Markdown、TXT 多种格式",
            "维度不统一：功能、定价、客户案例描述方式各异",
            "事实溯源困难：报告结论缺乏原始出处",
            "网络信息未验证：搜索补充的事实可能与内部资料冲突",
            "分析过程不可复现：不同人员结论差异大",
        ],
    },
    {
        "title": "二、整体解题思路",
        "bullets": [
            "多 Agent 流水线：每个 Agent 负责单一专业能力",
            "结构化中间产物：Pydantic 数据模型定义 KB / 分析 / 报告",
            "动态维度发现：不预设框架，维度由资料自然演化",
            "事实溯源：每条事实都带 SourceRef 来源引用",
            "人在环路：冲突记录等待人类专家裁决",
        ],
    },
    {
        "title": "多 Agent 架构",
        "bullets": [
            "ExpertAgent：读本地文档，抽取产品、维度、事实",
            "SearchAgent：网页搜索，抓取并提取结构化事实",
            "ExpertAgent（二次）：反向验证搜索事实",
            "RAGStore：向量索引，支持检索与验证",
            "AnalysisAgent：对比矩阵、量化评分、SWOT、差距、建议",
            "ReportAgent：综合生成最终报告",
        ],
    },
    {
        "title": "关键设计 1：动态维度发现",
        "bullets": [
            "不预设固定模板",
            "资料谈什么，维度就是什么",
            "避免信息被削足适履",
            "不同产品可以拥有不同维度",
        ],
    },
    {
        "title": "关键设计 2：事实溯源",
        "bullets": [
            "每条事实 = FactItem",
            "包含 content / status / confidence / source_refs",
            "source_refs 记录文档、页码/段落、原文引用",
            "任何结论都可回到原始资料验证",
        ],
    },
    {
        "title": "关键设计 3：搜索补充与反向验证",
        "bullets": [
            "SearchAgent 用 DuckDuckGo / Tavily 搜索网页",
            "LLM 从网页提取结构化事实",
            "ExpertAgent 将事实与原始资料比对",
            "状态：confirmed / external_supplement / conflict",
            "冲突进入 conflicts_and_clarifications 等待人工裁决",
        ],
    },
    {
        "title": "关键设计 4：分析层与报告层分离",
        "bullets": [
            "AnalysisAgent 输出结构化结果",
            "对比矩阵 / 评分排名 / SWOT / 差距 / 建议",
            "ReportAgent 基于结构化结果做叙事综合",
            "避免 ReportAgent 重复发明战略结论",
            "JSON 可被其他系统直接消费",
        ],
    },
    {
        "title": "关键设计 5：Agent 执行过程跟踪",
        "bullets": [
            "命令行添加 --trace 参数",
            "生成 {kb_id}_trace.md",
            "按 Agent 分章节展示中间产物",
            "可审计、可排查、可证明各 Agent 工作效果",
        ],
    },
    {
        "title": "关键设计 6：多 LLM Provider 支持",
        "bullets": [
            "Anthropic 官方 API",
            "OpenAI 兼容接口",
            "字节跳动火山方舟 Agent Plan",
            "通过 LLM_PROVIDER 环境变量切换",
            "业务代码几乎无需改动",
        ],
    },
    {
        "title": "运行效果与输出",
        "bullets": [
            "kb_xxxxxx.json / .md：结构化知识库",
            "kb_xxxxxx_report.json / .md：最终竞品分析报告",
            "kb_xxxxxx_trace.md：Agent 执行跟踪",
            "示例：CloudFlow CRM vs SalesMax Pro",
            "自动生成评分、排名、SWOT、战略建议",
        ],
    },
    {
        "title": "总结",
        "bullets": [
            "多 Agent 流水线替代单一大模型提示",
            "动态维度替代固定模板",
            "事实溯源 + 反向验证保证可信度",
            "结构化 JSON + Markdown 双输出",
            "Agent Trace 让分析过程透明可审计",
        ],
    },
]


class SlidePDF(FPDF):
    def header(self):
        pass

    def footer(self):
        self.set_y(-15)
        self.set_font("Custom", "", 10)
        self.set_text_color(128, 128, 128)
        self.cell(0, 10, f"{self.page_no()} / {len(slides)}", align="C")


pdf = SlidePDF("L", "mm", "A4")
pdf.add_font("Custom", "", font_path, uni=True)
pdf.set_auto_page_break(auto=False)

page_width = pdf.w
page_height = pdf.h
margin = 20

for idx, slide in enumerate(slides):
    pdf.add_page()
    # Light background
    pdf.set_fill_color(245, 245, 245)
    pdf.rect(0, 0, page_width, page_height, style="F")

    # Title bar
    pdf.set_fill_color(31, 78, 121)
    pdf.rect(0, 0, page_width, 35, style="F")

    pdf.set_xy(margin, 10)
    pdf.set_font("Custom", "", 24)
    pdf.set_text_color(255, 255, 255)
    pdf.cell(page_width - 2 * margin, 15, slide["title"], align="L")

    # Subtitle for title slide
    if slide.get("subtitle"):
        pdf.set_xy(margin, 80)
        pdf.set_font("Custom", "", 32)
        pdf.set_text_color(31, 78, 121)
        pdf.cell(page_width - 2 * margin, 20, slide["subtitle"], align="C")
        continue

    # Bullets
    pdf.set_xy(margin, 50)
    pdf.set_font("Custom", "", 18)
    pdf.set_text_color(51, 51, 51)

    for bullet in slide["bullets"]:
        pdf.set_x(margin)
        bullet_text = f"• {bullet}"
        pdf.multi_cell(page_width - 2 * margin, 12, bullet_text, align="L")
        pdf.ln(4)

pdf.output(output_path)
print(f"已生成 PDF：{output_path.resolve()}")
