"""
Search agent that discovers competitive intelligence from the web and feeds
structured findings back to the expert agent for knowledge base supplementation.
"""

import json
import os
import time
import uuid
from datetime import datetime
from typing import Any
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

from .models import FactItem, SearchResult, SourceRef
from .utils import extract_json_block


class SearchAgent:
    """
    Search agent for competitive intelligence.

    It performs web searches, fetches result pages, and uses an LLM to extract
    structured facts that can later be merged into the knowledge base by the
    expert agent.
    """

    def __init__(
        self,
        model: str | None = None,
        api_key: str | None = None,
        max_results: int = 5,
        fetch_timeout: int = 10,
        backend: str = "tavily",
        # backend options:
        #   - "tavily": real web search via Tavily API (requires TAVILY_API_KEY)
        #   - "duckduckgo": real web search via DuckDuckGo (free, no API key)
        #   - "mock": offline test mode, returns an empty result list, no network call
    ):
        from .llm_client import LLMClient

        self.client = LLMClient(api_key=api_key, model=model)
        self.max_results = max_results
        self.fetch_timeout = fetch_timeout
        self.backend = backend.lower()
        self._tavily_cache: dict[str, tuple[float, list[dict[str, Any]]]] = {}
        self._tavily_cache_ttl = 300  # 5 minutes

    def search(
        self,
        query: str,
        product_name: str,
        context: str | None = None,
    ) -> list[SearchResult]:
        """
        Execute a web search and extract structured facts from each result.

        Facts are extracted in one batched LLM call across all result pages to
        minimize round-trips.
        """
        print(f"🔍 搜索: {query}")
        raw_results = self._execute_search(query)
        print(f"   找到 {len(raw_results)} 条搜索结果")

        use_tavily_summary = self.backend == "tavily"

        # Collect page contents first
        pages: list[dict[str, Any]] = []
        for rank, item in enumerate(raw_results, start=1):
            title = item.get("title", "")
            url = item.get("href", "")
            snippet = item.get("body", "")

            if not url or not self._is_valid_url(url):
                continue

            print(f"   [{rank}] {title[:60]}... ({url})")

            if use_tavily_summary and snippet:
                page_content = self._clean_summary(snippet)
                print("      使用 Tavily 摘要，跳过网页抓取")
            else:
                page_content = self._fetch_page(url)
                if not page_content:
                    continue

            pages.append({
                "title": title,
                "url": url,
                "snippet": snippet,
                "page_content": page_content,
            })

        if not pages:
            return []

        # Extract facts from all pages in one LLM call
        url_to_facts = self._extract_facts_from_pages(query, pages, context)

        results: list[SearchResult] = []
        for page in pages:
            facts = url_to_facts.get(page["url"], [])
            results.append(
                SearchResult(
                    result_id=f"sr_{uuid.uuid4().hex[:8]}",
                    query=query,
                    product_name=product_name,
                    title=page["title"],
                    url=page["url"],
                    snippet=page["snippet"],
                    page_content=page["page_content"],
                    extracted_facts=facts,
                    searched_at=datetime.now().isoformat(),
                )
            )

        return results

    # Domains that are unlikely to contain useful competitive intelligence
    _BLOCKED_DOMAINS = {
        "dpboss", "satta", "matka", "lottery", "casino", "porn", "xxx",
        "bet", "gambling", "sex", "adult",
    }

    def _execute_search(self, query: str) -> list[dict[str, Any]]:
        """Run the search using the configured backend."""
        if self.backend == "duckduckgo":
            return self._search_duckduckgo(query)
        if self.backend == "tavily":
            return self._search_tavily(query)
        if self.backend == "mock":
            # Offline test mode: does not perform any real web search.
            return []
        raise ValueError(f"Unsupported search backend: {self.backend}")

    def _search_duckduckgo(self, query: str) -> list[dict[str, Any]]:
        """Run the search using DuckDuckGo."""
        try:
            from duckduckgo_search import DDGS
        except ImportError as exc:
            raise ImportError(
                "Please install duckduckgo-search: pip install duckduckgo-search"
            ) from exc

        with DDGS() as ddgs:
            return list(ddgs.text(query, max_results=self.max_results))

    def _search_tavily(self, query: str) -> list[dict[str, Any]]:
        """Run the search using Tavily API with a short-lived in-memory cache."""
        now = time.time()
        cached = self._tavily_cache.get(query)
        if cached:
            timestamp, results = cached
            if now - timestamp < self._tavily_cache_ttl:
                print("   使用 Tavily 缓存结果")
                return results

        api_key = os.getenv("TAVILY_API_KEY")
        if not api_key:
            raise ValueError(
                "TAVILY_API_KEY environment variable is required for Tavily backend"
            )

        try:
            from tavily import TavilyClient
        except ImportError as exc:
            raise ImportError(
                "Please install tavily: pip install tavily-python"
            ) from exc

        client = TavilyClient(api_key=api_key)
        response = client.search(
            query=query,
            max_results=self.max_results,
            search_depth="basic",
            include_answer=False,
        )
        results = [
            {
                "title": result.get("title", ""),
                "href": result.get("url", ""),
                "body": result.get("content", ""),
            }
            for result in response.get("results", [])
        ]
        self._tavily_cache[query] = (now, results)
        return results

    def _is_valid_url(self, url: str) -> bool:
        """Skip obviously non-web URLs and blocked domains."""
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            return False
        domain_lower = parsed.netloc.lower()
        return not any(bad in domain_lower for bad in self._BLOCKED_DOMAINS)

    def _fetch_page(self, url: str) -> str:
        """Fetch clean article text using Jina Reader, fallback to raw HTML parsing."""
        jina_url = f"https://r.jina.ai/http://{url}"
        try:
            response = requests.get(
                jina_url,
                timeout=(5, 15),
                headers={"Accept": "text/plain"},
            )
            response.raise_for_status()
            text = response.text.strip()
            if len(text) > 200:
                return text[:12_000]
        except Exception as exc:
            print(f"   ⚠️ Jina Reader 失败 ({url}): {exc}")

        # Fallback: raw page parsing with BeautifulSoup
        try:
            headers = {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                )
            }
            response = requests.get(
                url, headers=headers, timeout=(3, self.fetch_timeout)
            )
            response.raise_for_status()

            soup = BeautifulSoup(response.text, "html.parser")
            for tag in soup([
                "script", "style", "nav", "footer", "header", "aside",
                "noscript", "iframe", "form", "button",
            ]):
                tag.decompose()

            text = soup.get_text(separator="\n", strip=True)
            lines = [line.strip() for line in text.splitlines() if line.strip()]
            text = "\n".join(lines)
            return text[:12_000]
        except Exception as exc:
            print(f"   ⚠️ 无法获取页面 {url}: {exc}")
            return ""

    def _call_llm(self, prompt: str, max_tokens: int = 128000) -> str:
        return self.client.chat_completion(
            prompt=prompt,
            system="You are a careful web research assistant. Only use facts from the provided page.",
            max_tokens=max_tokens,
        )

    def _clean_summary(self, snippet: str) -> str:
        """Light cleaning of Tavily summary before LLM extraction."""
        lines = [line.strip() for line in snippet.splitlines() if line.strip()]
        seen = set()
        cleaned = []
        for line in lines:
            if len(line) < 8:
                continue
            key = line.lower()
            if key in seen:
                continue
            seen.add(key)
            cleaned.append(line)
        return "\n".join(cleaned[:20])

    def _extract_facts_from_pages(
        self,
        query: str,
        pages: list[dict[str, Any]],
        context: str | None,
    ) -> dict[str, list[FactItem]]:
        """Extract facts from all result pages in a single LLM call."""
        prompt = self._build_extraction_prompt(query, pages, context)
        response = self._call_llm(prompt, max_tokens=128000)
        return self._parse_facts(response, pages)

    def _build_extraction_prompt(
        self,
        query: str,
        pages: list[dict[str, Any]],
        context: str | None,
    ) -> str:
        context_section = (
            "\n## Background Context\n\n" + context + "\n" if context else ""
        )

        pages_text = ""
        page_template = """### Page {idx}
- Title: {title}
- URL: {url}
- Content:
{page_content}

"""
        for idx, page in enumerate(pages, start=1):
            pages_text += (
                page_template.replace("{idx}", str(idx))
                .replace("{title}", page["title"])
                .replace("{url}", page["url"])
                .replace("{page_content}", page["page_content"][:4000])
            )

        template = """You are a web research assistant for competitive intelligence.

Your task: read the pages below and extract factual information relevant to the search query. Return facts grouped by page URL.

## Search Query

{query}
{context_section}
## Pages

{pages_text}

## Instructions

1. Extract only factual claims directly supported by each page content.
2. Do not infer or add information from your own knowledge.
3. If a page has no useful information, return an empty facts array for that page.
4. Each fact should be a concise, self-contained sentence.
5. Categorize each fact with a `dimension_name` (e.g., "定价策略", "核心功能", "客户评价"). Do not use pre-defined dimensions.
6. Assign confidence: `high`, `medium`, or `low`.
7. **Extract at most 5 facts per page**, prioritizing query-relevant facts.

## Output Format

Return a JSON object mapping each URL to its facts:

```json
{
  "https://example.com/page1": [
    {
      "item_id": "i_001",
      "content": "concise factual statement",
      "dimension_name": "dimension name",
      "confidence": "high",
      "quote": "optional short quote"
    }
  ],
  "https://example.com/page2": []
}
```

Return only the JSON object, no additional explanation.
"""
        return (
            template.replace("{query}", query)
            .replace("{context_section}", context_section)
            .replace("{pages_text}", pages_text)
        )

    def _parse_facts(
        self, response: str, pages: list[dict[str, Any]]
    ) -> dict[str, list[FactItem]]:
        """Parse the LLM response into a URL -> facts mapping."""
        try:
            data = extract_json_block(response)
        except json.JSONDecodeError as exc:
            print(f"   ⚠️ 无法解析批量事实提取结果: {exc}")
            return {page["url"]: [] for page in pages}

        if not isinstance(data, dict):
            print("   ⚠️ 批量事实提取结果不是对象")
            return {page["url"]: [] for page in pages}

        url_to_facts: dict[str, list[FactItem]] = {}
        for page in pages:
            url = page["url"]
            facts_data = data.get(url, [])
            if not isinstance(facts_data, list):
                url_to_facts[url] = []
                continue
            url_to_facts[url] = self._facts_from_list(facts_data, page["title"], url)

        return url_to_facts

    def _facts_from_list(
        self, data: list[dict[str, Any]], title: str, url: str
    ) -> list[FactItem]:
        """Convert a list of raw fact dicts into FactItem objects."""
        facts: list[FactItem] = []
        for item in data:
            if not isinstance(item, dict):
                continue
            content = item.get("content", "").strip()
            if not content:
                continue

            source_ref = SourceRef(
                doc_id=f"web_{uuid.uuid4().hex[:8]}",
                file_name=title or url,
                page_or_section=url,
                quote=item.get("quote") or None,
                location_hint="web search result",
            )

            facts.append(
                FactItem(
                    item_id=item.get("item_id", f"i_{uuid.uuid4().hex[:6]}"),
                    content=content,
                    source_refs=[source_ref],
                    status="external_supplement",
                    confidence=item.get("confidence", "medium"),
                    added_by="search_agent",
                    note=f"dimension: {item.get('dimension_name', '未分类')}",
                )
            )
        return facts
