"""Live smoke test for the four MCP tools.

Run with:
    uv run python scripts/smoke_test.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from mcp import Client
from mcp.client.stdio import StdioServerParameters

PROJECT_ROOT = Path(__file__).resolve().parents[1]


async def main() -> int:
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "yuanbao_search_mcp"],
        cwd=str(PROJECT_ROOT),
    )
    remaining_calls = [
        (
            "yuanbao_search_academic",
            {"query": "大模型推理", "limit": 3, "include_summary": False},
        ),
        (
            "yuanbao_search_web",
            {"query": "人工智能", "limit": 3, "scope": "all"},
        ),
    ]
    failures = 0
    async with Client(params, read_timeout_seconds=120) as client:
        tools = await client.list_tools()
        expected_tools = {
            "yuanbao_search_weixin_articles",
            "yuanbao_read_weixin_article",
            "yuanbao_search_academic",
            "yuanbao_search_web",
        }
        names = {tool.name for tool in tools.tools}
        print("tools:", sorted(names))
        if names != expected_tools:
            print("unexpected tool set:", names)
            failures += 1

        weixin = await client.call_tool(
            "yuanbao_search_weixin_articles",
            {"query": "自进化", "limit": 1},
        )
        if weixin.is_error:
            print("weixin search failed:", weixin.content)
            failures += 1
        else:
            results = (weixin.structured_content or {}).get("results") or []
            if not results:
                print("weixin search returned no results")
                failures += 1
            else:
                url = results[0]["url"]
                article = await client.call_tool(
                    "yuanbao_read_weixin_article",
                    {"url": url, "max_chars": 2000},
                )
                if article.is_error:
                    print("article read failed:", article.content)
                    failures += 1
                else:
                    chars = (article.structured_content or {}).get("char_count") or 0
                    print("article chars:", chars)
                    if chars <= 0:
                        failures += 1

        for name, args in remaining_calls:
            result = await client.call_tool(name, args)
            data = result.structured_content or {}
            if result.is_error:
                print(name, "failed:", result.content)
                failures += 1
            elif name == "yuanbao_search_academic":
                core_papers = data.get("core_papers") or []
                sub_questions = data.get("sub_questions") or []
                summary = data.get("summary") or ""
                summary_truncated = data.get("summary_truncated") or False
                warnings = data.get("warnings") or []
                print(
                    "academic:"
                    f" core_papers={len(core_papers)}"
                    f" sub_questions={len(sub_questions)}"
                    f" summary_chars={len(summary)}"
                    f" truncated={summary_truncated}"
                    f" warnings={warnings}"
                )
                if not core_papers or not sub_questions:
                    failures += 1
            else:
                results = data.get("results") or []
                related_queries = data.get("related_queries") or []
                warnings = data.get("warnings") or []
                print(
                    f"web: count={len(results)}"
                    f" related={related_queries}"
                    f" warnings={warnings}"
                )
                if not results:
                    failures += 1

    if failures:
        print(f"SMOKE FAILED ({failures})")
        return 1
    print("SMOKE OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
