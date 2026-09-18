# 多 Agent 竞品情报分析系统

一个由多个专家 Agent 协作的竞品情报 pipeline：从本地资料中动态发现维度、抽取结构化知识库，通过网页搜索补充并反向验证，最终生成对比矩阵、量化评分、SWOT、差距分析与可执行建议。

## 核心流程

```
本地资料 ──▶ ExpertAgent ──▶ KnowledgeBase
                                │
                                ▼
                         SearchAgent（网页搜索）
                                │
                                ▼
                         ExpertAgent（反向验证）
                                │
                                ▼
                         AnalysisAgent（对比 / 评分 / SWOT / 差距）
                                │
                                ▼
                         ReportAgent（最终报告）
```

1. **ExpertAgent**：读取本地竞品资料，自动识别产品、发现维度、抽取事实，构建 `KnowledgeBase`。
2. **SearchAgent**：默认使用 **Tavily** 搜索网页，抓取页面并提取结构化事实。
3. **ExpertAgent（验证）**：回到原始资料中验证搜索到的事实，标记为 `confirmed`、`external_supplement`、`conflict` 等。
4. **AnalysisAgent**：对比自有产品与竞品，输出对比矩阵、量化评分、SWOT、差距分析、行动建议。
5. **ReportAgent**：基于知识库与分析结果生成最终的竞品分析报告（JSON + Markdown）。

## 功能特性

- **多格式输入**：PDF、Word（.docx）、HTML、Markdown、TXT 等。
- **动态维度发现**：不预设框架，由 Agent 从资料中自然总结出实际存在的维度。
- **来源可追溯**：每条事实都标注来源文件、页码/段落和引用。
- **事实状态机**：`confirmed`、`pending_verification`、`external_supplement`、`not_mentioned`、`conflict`。
- **网页搜索补充**：默认 Tavily，支持 DuckDuckGo 和离线 mock 模式。
- **反向验证**：搜索事实必须经过原始资料验证，避免直接采用网络谣言。
- **竞品对比分析**：对比矩阵、量化评分/排名、SWOT、差距分析、优先级建议。
- **结构化报告**：最终报告包含执行摘要、市场概述、产品定位、关键发现、战略建议、风险与下一步行动。
- **Agent 执行跟踪**：`--trace` 输出每个 Agent 的中间 Markdown 产物。
- **构建兜底**：一次性抽取被截断时，自动降级为按产品逐个抽取。
- **多 LLM Provider**：Anthropic、OpenAI 兼容接口、火山方舟 Agent Plan。

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

支持的 LLM provider：

- **Anthropic（默认）**
  ```bash
  LLM_PROVIDER=anthropic
  ANTHROPIC_API_KEY=your_anthropic_api_key
  ANTHROPIC_MODEL=claude-sonnet-4-20250514
  ```

- **OpenAI 兼容接口（如火山方舟 / Doubao）**
  ```bash
  LLM_PROVIDER=openai
  OPENAI_API_KEY=your_api_key
  OPENAI_BASE_URL=https://ark.cn-beijing.volces.com/api/v3
  OPENAI_MODEL=doubao-pro-32k
  ```

- **Anthropic 兼容接口（火山方舟 also 支持）**
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

  > Agent Plan 使用与普通 Ark API 不同的专属 Key，可在火山方舟控制台“API Key 管理”中创建。
  >
  > 代码中所有 LLM 调用默认请求 `max_tokens=128000`，但 provider 会按自身上限截断，代码会自动裁剪并打印提示：
  > - `volcano-agent-plan`：使用 `max_completion_tokens`，上限 **32768**（ark-code-latest 最大输出）。
  > - `anthropic`：上限 **8192**。
  > - `openai`：保留 128000，由具体模型决定实际上限。

### 3. 端到端运行

最简单的方式是直接运行提供的脚本：

```bash
./run_pipeline.sh
```

默认流程：
1. 从 `examples/sample_competitive_materials.md` 构建知识库。
2. 使用 Tavily 搜索补充知识库（必须运行）。
3. 运行分析并生成最终报告。

常用参数：

```bash
./run_pipeline.sh --trace
./run_pipeline.sh --search-backend duckduckgo --max-results 5
./run_pipeline.sh --own-product "方舟 Agent Plan"
```

### 4. 分步使用

#### 构建知识库

```bash
python -m src.main build examples/sample_competitive_materials.md
```

标记自有产品：

```bash
python -m src.main build examples/sample_competitive_materials.md --own-product "方舟 Agent Plan"
```

> **输入来源**：`build` 子命令接受任意可阅读文档路径（PDF、Word、Markdown、TXT、HTML）。把资料放在 `examples/` 目录下即可，也可以直接传入自己的文件路径。
>
> **抽取兜底**：如果一次性输出超过模型 token 上限被截断，`ExpertAgent` 会自动切换为“先识别产品清单，再逐个产品抽取”。

输出：

```
output/
  kb_xxxxxx.json
  kb_xxxxxx.md
```

#### 网页搜索补充

默认使用 Tavily：

```bash
python -m src.main search output/kb_xxxxxx.json "方舟 Agent Plan" "方舟 Agent Plan 客户评价"
```

切换搜索引擎：

```bash
# DuckDuckGo（免费，部分网络环境不稳定）
python -m src.main search output/kb_xxxxxx.json "方舟 Agent Plan" "方舟 Agent Plan 客户评价" --search-backend duckduckgo

# mock（离线测试，不发起真实搜索，直接返回空结果）
python -m src.main search output/kb_xxxxxx.json "方舟 Agent Plan" "方舟 Agent Plan 客户评价" --search-backend mock
```

调整搜索返回结果数量：

```bash
python -m src.main search output/kb_xxxxxx.json "方舟 Agent Plan" "方舟 Agent Plan 客户评价" --max-results 5
```

`--max-results` 默认值为 3，控制搜索 Agent 最多处理多少条搜索结果。

#### 运行竞品分析

```bash
python -m src.main analyze output/kb_xxxxxx.json
```

分析时直接生成最终报告：

```bash
python -m src.main analyze output/kb_xxxxxx.json --generate-report
```

#### 生成最终报告

```bash
python -m src.main report output/kb_xxxxxx.json
```

### 5. Agent 执行跟踪

使用 `--trace` 可在每个阶段输出 Markdown 形式的中间产物：

```bash
python -m src.main build examples/sample_competitive_materials.md --own-product "方舟 Agent Plan" -o output --trace
python -m src.main analyze output/kb_xxxxxx.json --generate-report -o output --trace
```

会生成 `output/{kb_id}_trace.md`，包含：

1. **ExpertAgent**：识别到的产品、维度、关键事实、自有产品、冲突数。
2. **SearchAgent**：搜索页面、提取事实数、关键事实。
3. **ExpertAgent（验证）**：补充后事实数、状态分布。
4. **AnalysisAgent**：对比矩阵、量化评分与排名、SWOT、差距分析、行动建议。
5. **ReportAgent**：执行摘要、市场概述、产品定位、关键发现、战略建议、下一步行动。

多次运行同一 KB 时，跟踪文件会自动追加。

## 输出文件

运行完整 pipeline 后，`output/` 目录下会生成：

```
output/
  kb_xxxxxx.json          # 结构化知识库
  kb_xxxxxx.md            # 知识库 Markdown 报告
  kb_xxxxxx_report.json   # 最终结构化报告
  kb_xxxxxx_report.md     # 最终 Markdown 报告
  kb_xxxxxx_trace.md      # Agent 中间产物（启用 --trace 时）
```

## CLI 命令速查

| 命令 | 作用 | 常用参数 |
|---|---|---|
| `build` | 从本地文档构建知识库 | `--own-product`, `--output-dir`, `--trace` |
| `search` | 搜索网页并补充知识库 | `--search-backend`, `--max-results`, `--output-dir`, `--trace` |
| `analyze` | 竞品对比分析 | `--generate-report`, `--criteria-file`, `--output-dir`, `--trace` |
| `report` | 生成最终报告 | `--output-dir`, `--trace` |

全局参数：

- `--model`：覆盖默认模型。
- `-o / --output-dir`：输出目录，默认 `output/`。
- `--trace`：启用 Agent 中间产物跟踪。

## 设计说明

### 动态维度

专家 Agent 在阅读完资料后，自主判断应该提取哪些维度。例如：

- 如果资料重点讨论“定价策略”和“客户案例”，则这两个成为维度。
- 如果某产品只提到“目标用户”，则只生成该维度，不会为空洞地填充“定价”。

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
┌────────────────────────────────────────────────────┐
│ 更新知识库：confirmed / external_supplement / conflict │
└────────────────────────────────────────────────────┘
       │
       ▼
┌──────────────┐     ┌──────────────┐
│  分析 Agent   │ ──▶ │  报告 Agent   │
└──────────────┘     └──────────────┘
```

## 项目结构

```
business_analysis_agent/
├── src/
│   ├── __init__.py
│   ├── models.py              # Pydantic 动态知识库数据模型
│   ├── parser.py              # 多格式文档解析
│   ├── llm_client.py          # 统一 LLM 客户端（多 provider）
│   ├── expert_agent.py        # 专家 Agent：抽取、验证、合并
│   ├── search_agent.py        # 搜索 Agent：网页搜索与事实提取
│   ├── analysis_agent.py      # 分析 Agent：对比矩阵、评分、SWOT
│   ├── report_agent.py        # 报告专家 Agent：最终报告
│   ├── report_generator.py    # Markdown 报告生成
│   ├── trace_logger.py        # Agent 中间输出 Markdown 跟踪
│   ├── rag_store.py           # Milvus Lite 向量存储
│   ├── embeddings.py          # 向量模型缓存
│   └── main.py                # CLI 入口
├── examples/                  # 示例竞品资料
├── output/                    # 输出目录
├── run_pipeline.sh            # 端到端脚本
├── requirements.txt
├── .env.example
└── README.md
```

## 注意事项

- `.env` 文件用于存放真实 API Key，已被 `.gitignore` 忽略；`.env.example` 是模板，不要写入真实 Key。
- 当前版本适用于单篇或少量文档。超长文档会自动按段落分块处理；`build` 阶段如果一次性输出超过模型上限，会自动降级为按产品逐个抽取。
- 网页搜索默认使用 **Tavily**（需要 `TAVILY_API_KEY`），更稳定；也可切换为 DuckDuckGo（免费，部分网络环境不稳定）或 `mock`（离线测试，不发起真实搜索）。
- 所有 LLM 调用默认请求 `max_tokens=128000`，但 provider 会按自身上限截断（火山 Agent Plan 为 32768，Anthropic 为 8192），代码里会自动裁剪并打印提示。
- 输出质量取决于输入资料和搜索结果页面的清晰度。
