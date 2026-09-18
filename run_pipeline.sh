#!/bin/bash
#
# 端到端运行脚本：build → search → analyze --generate-report
#
# 用法：
#   ./run_pipeline.sh
#   ./run_pipeline.sh --no-trace
#   ./run_pipeline.sh --search-backend mock
#   ./run_pipeline.sh --search-backend duckduckgo --max-results 5
#   ./run_pipeline.sh --own-product "CloudFlow CRM"
#
# 默认启用 --trace，每个 Agent 的中间输出会写入 output/{kb_id}_trace.md。

set -e

OUTPUT_DIR="output"
# 必须与文档中的产品名称一致，否则无法标记为自有产品
OWN_PRODUCT="方舟 Agent Plan"
SEARCH_BACKEND="tavily"
MAX_RESULTS=5
# 默认开启 Agent 中间产物跟踪
TRACE="--trace"

while [[ $# -gt 0 ]]; do
  case $1 in
    --trace)
      TRACE="--trace"
      shift
      ;;
    --no-trace)
      TRACE=""
      shift
      ;;
    --search-backend)
      SEARCH_BACKEND="$2"
      shift 2
      ;;
    --max-results)
      MAX_RESULTS="$2"
      shift 2
      ;;
    --own-product)
      OWN_PRODUCT="$2"
      shift 2
      ;;
    --output-dir)
      OUTPUT_DIR="$2"
      shift 2
      ;;
    *)
      echo "未知参数: $1" >&2
      echo "用法: $0 [--trace] [--no-trace] [--search-backend mock|duckduckgo|tavily] [--max-results N] [--own-product NAME] [--output-dir DIR]" >&2
      exit 1
      ;;
  esac
done

# 切换到脚本所在目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

SAMPLE_DOC="examples/sample_competitive_materials.md"
if [[ ! -f "$SAMPLE_DOC" ]]; then
  echo "❌ 示例资料不存在：$SAMPLE_DOC" >&2
  exit 1
fi

echo ""
echo "============================================"
echo " 竞品专家多 Agent 系统 - 端到端 Pipeline"
echo "============================================"
echo " 自有产品: $OWN_PRODUCT"
echo " 搜索后端: $SEARCH_BACKEND"
echo " 搜索结果: $MAX_RESULTS"
echo " 输出目录: $OUTPUT_DIR"
echo "============================================"

# Step 1: build
echo ""
echo "[1/3] 正在从本地文档构建知识库..."
python -m src.main build "$SAMPLE_DOC" \
  --own-product "$OWN_PRODUCT" \
  -o "$OUTPUT_DIR" \
  $TRACE

# 找到最新的知识库 JSON
KB_FILE=$(ls -t "$OUTPUT_DIR"/kb_*.json 2>/dev/null | head -n 1)
if [[ -z "$KB_FILE" ]]; then
  echo "❌ 未找到生成的知识库 JSON 文件" >&2
  exit 1
fi
echo "📚 构建完成：$KB_FILE"

# Step 2: search（必须运行）
echo ""
echo "[2/3] 正在通过网页搜索补充知识库..."
python -m src.main search "$KB_FILE" "$OWN_PRODUCT" "$OWN_PRODUCT 客户评价" \
  --search-backend "$SEARCH_BACKEND" \
  --max-results "$MAX_RESULTS" \
  -o "$OUTPUT_DIR" \
  $TRACE

KB_FILE=$(ls -t "$OUTPUT_DIR"/kb_*.json 2>/dev/null | head -n 1)
if [[ -z "$KB_FILE" ]]; then
  echo "❌ 搜索补充后未找到知识库 JSON 文件" >&2
  exit 1
fi
echo "🔍 搜索补充完成：$KB_FILE"

# Step 3: analyze + report
echo ""
echo "[3/3] 正在运行竞品分析并生成最终报告..."
python -m src.main analyze "$KB_FILE" \
  --generate-report \
  -o "$OUTPUT_DIR" \
  $TRACE

KB_ID=$(basename "$KB_FILE" .json)

echo ""
echo "============================================"
echo " ✅ 端到端 Pipeline 运行完成"
echo "============================================"
echo " 知识库 JSON:     $OUTPUT_DIR/${KB_ID}.json"
echo " 知识库 Markdown: $OUTPUT_DIR/${KB_ID}.md"
echo " 最终报告 JSON:   $OUTPUT_DIR/${KB_ID}_report.json"
echo " 最终报告 Markdown: $OUTPUT_DIR/${KB_ID}_report.md"
if [[ -n "$TRACE" ]]; then
  echo " 跟踪日志:        $OUTPUT_DIR/${KB_ID}_trace.md"
fi
echo "============================================"
