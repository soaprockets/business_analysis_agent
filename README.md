# 竞品专家 Agent + 搜索 Agent

从任意可阅读竞品资料中自动提取结构化知识库，维度不由人工预定义，而是由专家 Agent 根据资料内容动态发现。搜索 Agent 可以通过网页搜索发现新的竞品信息，并反馈给专家 Agent 进行反向验证和补充。

## 功能特性

- **多格式支持**：PDF、Word（.docx）、HTML、Markdown、TXT 等。
- **动态维度发现**：不预设"定位/功能/定价"等固定框架，由 Agent 从文本中自然总结出实际存在的维度。
- **双形态输出**：
  - 机器可用的 JSON 知识库
  - 人类可读的 Markdown 报告
- **来源可追溯**：每条知识点都标注来源文件、页码/段落和引用。
- **事实状态管理**：支持 `confirmed`、`pending_verification`、`external_supplement`、`not_mentioned`、`conflict` 等状态。
- **网页搜索补充**：搜索 Agent 默认通过 Tavily 搜索竞品信息（支持切换 DuckDuckGo 或离线 mock），提取结构化事实。
- **反向验证**：专家 Agent 会回到原始资料中验证搜索结果，确认、标注外部补充或记录冲突。
- **分析 Agent**：从知识库中对比自有产品与竞品，生成对比矩阵、量化评分、SWOT、差距分析与行动建议。
- **人类在环路中**：遇到信息冲突时，记录到 `conflicts_and_clarifications` 等待人类专家裁决。
- **Agent 执行跟踪**：使用 `--trace` 输出每个 Agent 的中间 Markdown 产物，便于审计与验证。
- **多 LLM Provider 支持**：兼容 Anthropic、OpenAI 兼容接口以及火山方舟 Agent Plan。
- **构建兜底**：`ExpertAgent` 先尝试一次性抽取全部产品；如果输出被截断导致 JSON 解析失败，会自动降级为“按产品逐个抽取”，避免触碰到模型的输出 token 上限。

## 快速开始

### 1. 安装依赖

```bash
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 2. 配置 API Key

```bash
cp .env.example .env
# 编辑 .env，选择 LLM provider 并填入对应 API Key
```

支持两种 LLM provider：

- **Anthropic（默认）**
  ```bash
  LLM_PROVIDER=anthropic
  ANTHROPIC_API_KEY=your_anthropic_api_key
  ANTHROPIC_MODEL=claude-sonnet-4-20250514
  ```

- **OpenAI 兼容接口（如字节跳动火山方舟 / Doubao）**
  ```bash
  LLM_PROVIDER=openai
  OPENAI_API_KEY=your_ark_api_key
  OPENAI_BASE_URL=https://ark.cn-beijing.volces.com/api/v3
  OPENAI_MODEL=doubao-pro-32k
  ```

- **Anthropic 兼容接口（字节跳动火山方舟 also 支持）**
  ```bash
  LLM_PROVIDER=anthropic
  ANTHROPIC_API_KEY=your_ark_api_key
  ANTHROPIC_BASE_URL=https://ark.cn-beijing.volces.com/api/v3/anthropic
  ANTHROPIC_MODEL=ark-code-latest
  ```

- **火山方舟 Agent Plan（OpenAI 兼容接口）**
  ```bash
  LLM_PROVIDER=volcano-agent-plan
  VOLCANO_AGENT_API_KEY=your_agent_plan_api_key
  VOLCANO_AGENT_BASE_URL=https://ark.cn-beijing.volces.com/api/plan/v3
  VOLCANO_AGENT_MODEL=ark-code-latest
  ```
  > Agent Plan 使用与普通 Ark API 不同的专属 Key，具体可在火山方舟控制台“API Key 管理”中创建。
  >
  > 代码中所有 LLM 调用的 `max_tokens` 默认请求 **128000**，但不同 provider 有各自的输出上限，超出会被自动裁剪：
  > - `volcano-agent-plan`：使用 `max_completion_tokens`，上限 **32768**（ark-code-latest 最大输出）。
  > - `anthropic`：上限 **8192**。
  > - `openai`：保留 128000，由具体模型决定实际上限。

当前项目已默认配置为字节跳动火山方舟（Agent Plan 模式）。

### 3. 从本地文档构建知识库

```bash
python -m src.main build examples/sample_competitive_materials.md
```

如果资料中包含我们自己的产品，可以在构建时标记，便于后续分析：

```bash
python -m src.main build examples/sample_competitive_materials.md --own-product "CloudFlow CRM"
```

输出默认保存在 `output/` 目录：

```
output/
  kb_xxxxxx.json
  kb_xxxxxx.md
```

> **抽取兜底**：`build` 默认尝试一次性提取所有产品。如果返回的 JSON 因输出 token 上限被截断，会自动切换为“先识别产品清单，再逐个产品抽取”。你不需要额外参数。

### 4. 通过网页搜索补充知识库

默认使用 Tavily（更稳定，需要 API Key）：

```bash
# 在 .env 中配置 TAVILY_API_KEY
python -m src.main search output/kb_xxxxxx.json "CloudFlow CRM" "CloudFlow CRM 客户评价"
```

如果不需要 API Key，可以使用 DuckDuckGo（免费，但部分网络环境不稳定）：

```bash
python -m src.main search output/kb_xxxxxx.json "CloudFlow CRM" "CloudFlow CRM 客户评价" --search-backend duckduckgo
```

仅用于测试流程，不发起真实搜索（离线模式，直接返回空结果）：

```bash
python -m src.main search output/kb_xxxxxx.json "CloudFlow CRM" "CloudFlow CRM 客户评价" --search-backend mock
```

搜索 Agent 会：

1. 在网页上搜索关键词。
2. 抓取搜索结果页面。
3. 用 LLM 提取结构化事实。
4. 把这些事实交给专家 Agent。
5. 专家 Agent 回到原始资料中验证这些事实。
6. 把验证后的结果补充进知识库，重新生成 JSON 和 Markdown 报告。

### 5. 运行竞品分析

在已有知识库上运行分析 Agent，生成对比矩阵、量化评分、SWOT、差距分析与建议：

```bash
python -m src.main analyze output/kb_xxxxxx.json
```

分析结果会追加到原知识库中，Markdown 报告会增加“五、竞争分析”章节。

### 6. 生成最终竞品分析报告

调用报告专家 Agent，基于知识库和分析结果生成结构化的最终报告：

```bash
python -m src.main report output/kb_xxxxxx.json
```

或者在分析时直接生成最终报告：

```bash
python -m src.main analyze output/kb_xxxxxx.json --generate-report
```

报告专家 Agent 会输出：

- `output/kb_xxxxxx_report.json`：结构化报告数据
- `output/kb_xxxxxx_report.md`：可直接阅读的最终 Markdown 报告

内容包括执行摘要、市场概述、各产品定位、关键发现、SWOT 综合、差距综合、战略建议、风险与冲突、下一步行动等。

## Agent 执行过程跟踪

使用 `--trace` 参数可以在每个命令执行时输出 Markdown 形式的 Agent 中间产物，用于验证每个阶段的工作效果：

```bash
python -m src.main build examples/sample_competitive_materials.md --own-product "CloudFlow CRM" -o output --trace
python -m src.main analyze output/kb_xxxxxx.json --generate-report -o output --trace
python -m src.main report output/kb_xxxxxx.json -o output --trace
```

启用后会生成 `output/{kb_id}_trace.md`，按 Agent 分章节展示：

1. **ExpertAgent**：识别到的产品、维度、关键事实、自有产品、冲突数。
2. **SearchAgent**：搜索页面、提取事实数、关键事实。
3. **ExpertAgent（验证）**：补充后事实数、状态分布。
4. **AnalysisAgent**：对比矩阵、量化评分与排名、SWOT、差距分析、行动建议。
5. **ReportAgent**：执行摘要、市场概述、产品定位、关键发现、战略建议、下一步行动。

多次运行同一 KB 时，跟踪文件会自动追加，便于对比不同阶段的输出。

## 项目结构

```
business_analysis_agent/
├── src/
│   ├── __init__.py
│   ├── models.py              # 动态知识库数据模型
│   ├── parser.py              # 多格式文档解析
│   ├── expert_agent.py        # 专家 Agent 核心逻辑
│   ├── search_agent.py        # 搜索 Agent 核心逻辑
│   ├── analysis_agent.py      # 分析 Agent 核心逻辑
│   ├── report_agent.py        # 报告专家 Agent 核心逻辑
│   ├── report_generator.py    # Markdown 报告生成
│   ├── trace_logger.py        # Agent 中间输出 Markdown 跟踪
│   └── main.py                # CLI 入口
├── examples/                  # 放置竞品资料
├── output/                    # 输出目录
├── requirements.txt
├── .env.example
└── README.md
```

## 设计说明

### 动态维度

专家 Agent 在阅读完资料后，会自主判断应该提取哪些维度。例如：

- 如果资料重点讨论"定价策略"和"客户案例"，则这两个成为维度。
- 如果某产品只提到"目标用户"，则只生成该维度，不会为空洞地填充"定价"。

### 严格基于文档

Agent 的 prompt 明确要求：

1. 只使用文档中明确出现的信息。
2. 不能依赖模型自身的知识补充事实。
3. 不确定或缺失的信息标注为 `pending_verification` 或 `not_mentioned`。

### 搜索 Agent 与专家 Agent 的协作流程

```
┌──────────────┐     网页搜索      ┌──────────────┐
│  搜索 Agent   │ ───────────────▶ │  抓取网页内容  │
└──────────────┘                  └──────────────┘
       │                                  │
       │                                  ▼
       │                         ┌──────────────┐
       │                         │  LLM 提取事实 │
       │                         └──────────────┘
       │                                  │
       ▼                                  ▼
┌──────────────┐     结构化事实     ┌──────────────┐
│  专家 Agent   │ ◀─────────────── │  搜索 Agent   │
└──────────────┘                   └──────────────┘
       │
       │ 回到原始资料中反向验证
       ▼
┌──────────────┐
│ 更新知识库    │
│ confirmed /  │
│ external_    │
│ supplement / │
│ conflict     │
└──────────────┘
       │
       ▼
┌──────────────┐
│  分析 Agent   │  对比矩阵 / 评分 / SWOT / 差距 / 建议
└──────────────┘
```

## 注意事项

- 当前版本适用于单篇或少量文档。超长文档会自动按段落分块处理；`build` 阶段如果一次性输出超过模型上限，会自动降级为按产品逐个抽取。
- 网页搜索默认使用 **Tavily**（需要 `TAVILY_API_KEY`），更稳定；也可切换为 DuckDuckGo（免费，部分网络环境不稳定）或 `mock`（离线测试，不发起真实搜索）。
- 输出质量取决于输入资料和搜索结果页面的清晰度。
- `.env` 文件用于存放真实 API Key，已被 `.gitignore` 忽略；`.env.example` 是模板，不要写入真实 Key。
- 所有 LLM 调用默认请求 `max_tokens=128000`，但 provider 会按自身上限截断（火山 Agent Plan 为 32768，Anthropic 为 8192），代码里会自动裁剪并打印提示。
