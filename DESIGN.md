# yuanbao-search-mcp — Design Decisions

> Status: agreed in grilling session, 2026-11-12
> Scope: v0.1.0, personal use, pure HTTP (no Playwright)

---

## 1. Goal and scope

Build a standard MCP server that exposes the useful, pure-HTTP capabilities of
Tencent Yuanbao Search (`so.qq.com`) to MCP clients such as OpenCode, Claude
Desktop, Cursor, and Claude Code.

### In scope

| Tool | Purpose |
|---|---|
| `yuanbao_search_weixin_articles` | Search WeChat official-account articles |
| `yuanbao_read_weixin_article` | Read a WeChat article's full text |
| `yuanbao_search_academic` | Academic search: core papers, sub-questions, optional AI summary |
| `yuanbao_search_web` | General web search: all / gov / media |

### Out of scope (v0.1.0)

- Yuanbao AI mode Q&A (requires Playwright/signed SSE)
- Video search (client-rendered, requires Playwright)
- Image search
- Server-side time filter (not available via URL)
- Read counts, likes, comments
- Academic figures / mind maps
- Login-only features (history, favorites)
- Boolean operators / `site:` (upstream does not support them)
- Docker image, PyPI publishing

Rationale: the official Tencent Cloud `SearchPro` API exists but explicitly
excludes WeChat official-account content. The unofficial `so.qq.com` HTTP
surface is the only way to cover 公众号, which is the core value of this MCP.

---

## 2. Runtime and packaging

- Python `>=3.11`
- `uv` project, console script `yuanbao-search-mcp`
- Dependencies: `mcp>=2,<3`, `httpx`, `beautifulsoup4`, `lxml`,
  `pydantic>=2`, `pydantic-settings`
- Dev dependencies: `pytest`, `pytest-asyncio`, `respx`, `ruff`
- `pip` / `pipx` documented as fallback
- MIT license for code; upstream data remains with its original owners
- Git repository with initial commit
- GitHub Actions: `uv sync`, `ruff check`, `pytest` (no live-network tests)
- Bilingual README:
  - `README.md` — English (GitHub default)
  - `README.zh-CN.md` — Chinese
  - Each starts with `[English](README.md) | [简体中文](README.zh-CN.md)`

---

## 3. Tool contracts

### 3.1 `yuanbao_search_weixin_articles`

Search WeChat official-account articles via
`GET https://so.qq.com/isearch?query=<q>&tab=weixin_article`.

**Input**

| Field | Type | Default | Rules |
|---|---|---|---|
| `query` | `str` | — | Required unless `account` is provided; no explicit length cap |
| `account` | `str \| null` | `null` | Restrict to an account; contains match, case-insensitive |
| `limit` | `int` | `20` | 1–28 |
| `sort` | `"relevance" \| "date"` | `"relevance"` | `date` = publish time desc |
| `days` | `int \| null` | `null` | >= 1; local filter by publish date |

**Query composition**

- If `account` and `query`: upstream query = `"<account> <query>"`.
- If only `account`: upstream query = `"<account>"`.
- If only `query`: upstream query = `"<query>"`.
- At least one of `query` / `account` must be non-empty.

**Output**

```json
{
  "query": "...",
  "account": "量子位",
  "count": 20,
  "total_available": 28,
  "results": [
    {
      "title": "...",
      "account": "量子位",
      "publish_time": "2026-11-12",
      "summary": "...",
      "url": "https://mp.weixin.qq.com/s?...",
      "doc_id": "...",
      "cover_url": "https://mmbiz.qpic.cn/...",
      "date_unknown": false
    }
  ],
  "warnings": []
}
```

- Strip highlight private-use characters `\ue40a` / `\ue40b`.
- Normalize `http://mp.weixin.qq.com/...` to `https://`.
- `days` filter: keep undated results with `date_unknown=true` and add a warning.
- `sort=date`: undated results go last, original order preserved among ties.
- Empty results: return `results: []` with a warning, not an error.
- Cache: 5 minutes, keyed by all inputs.

### 3.2 `yuanbao_read_weixin_article`

Fetch and parse a WeChat article from `mp.weixin.qq.com`.

**Input**

| Field | Type | Default | Rules |
|---|---|---|---|
| `url` | `str` | — | http/https, host must be `mp.weixin.qq.com` |
| `max_chars` | `int` | `20000` | 1,000–100,000 |

**Output**

```json
{
  "title": "...",
  "account": "...",
  "publish_time": "2026-11-12",
  "url": "https://mp.weixin.qq.com/s?...",
  "content": "lightweight Markdown body",
  "char_count": 5303,
  "original_chars": 5303,
  "truncated": false,
  "images": ["https://mmbiz.qpic.cn/..."],
  "image_count": 52
}
```

- Extract `#activity-name`, `#js_name`, `#publish_time`, `#js_content`.
- Convert body to lightweight Markdown: paragraphs, headings, lists,
  blockquotes; no inline HTML.
- Images: `data-src` first, then `src`; keep `mmbiz.qpic.cn` content images;
  exclude avatars/icons; dedupe; cap at 50 URLs.
- Truncate at a paragraph boundary; set `truncated=true` and `original_chars`.
- Detect error pages (`参数错误`, `该内容已被发布者删除`,
  `此内容因违规无法查看`, `环境异常`, `请在微信客户端打开链接`) and raise a
  classified `ToolError`.
- Cache: 30 minutes, keyed by URL + max_chars.

### 3.3 `yuanbao_search_academic`

Search the 学术科普 tab. Uses the page-created `sessionId` and two internal
endpoints.

**Input**

| Field | Type | Default | Rules |
|---|---|---|---|
| `query` | `str` | — | Required; no explicit length cap |
| `limit` | `int` | `10` | 1–20; controls core papers only |
| `include_summary` | `bool` | `false` | AI academic summary |
| `summary_timeout` | `float` | `45` | 5–120 seconds |
| `include_subquestions` | `bool` | `true` | 8 sub-questions × 4 papers |

**Output**

```json
{
  "query": "...",
  "core_papers": [
    {
      "citation_id": 1,
      "title": "...",
      "authors": ["..."],
      "venue": "...",
      "year": "2025",
      "cited_by": 1011,
      "url": "https://doi.org/...",
      "abstract": "...",
      "abstract_truncated": false,
      "evidence": [
        {"quote_number": 1, "quote": "..."}
      ]
    }
  ],
  "sub_questions": [
    {
      "question": "...",
      "papers": [
        {
          "title": "...",
          "venue": "arXiv",
          "year": "2025",
          "url": "https://arxiv.org/abs/...",
          "abstract_short": "..."
        }
      ]
    }
  ],
  "summary": null,
  "summary_truncated": false,
  "summary_char_count": 0,
  "warnings": []
}
```

- Core papers from `academic_agent/frame_get` with `get_sup=1`.
- Sub-questions from `vertical_hub/academic/search_for_subq`; 8 × 4 papers.
- `limit` only controls core papers (default 10, max 20).
- Core abstracts capped at 1,200 chars; sub-question abstracts at 300 chars.
- Evidence: top 2 quotes per core paper, each capped at 300 chars.
- AI summary: off by default; env `YUANBAO_ACADEMIC_SUMMARY_DEFAULT=true` can
  flip the default. On timeout, return partial summary with
  `summary_truncated=true` and a warning.
- If `get_sup` fails but sub-questions succeed, return sub-questions + warning.
  If both fail, raise `ToolError`.
- Remove `<figure ...></figure>` placeholders from the summary; note
  `figures_omitted` in warnings if any were removed.
- Cache: 10 minutes, keyed by all inputs including summary flags.

**Endpoints**

1. `GET https://so.qq.com/isearch?query=<q>&tab=xueshu` → extract `sessionId`
   (regex on the RSC payload; fallback to `uuid`).
2. `POST https://lizhiassistant.search.qq.com/vertical_hub/academic/search_for_subq`
   body: `{"query": "...", "uuid": "<sid>", "guid": "", "session_id": "<sid>"}`
3. `POST https://lizhiassistant.search.qq.com/academic_agent/frame_get`
   body: `{"session_id": "<sid>", "get_sup": 1, "pass_through": ""}`
4. Summary frames: same `frame_get` with `{"session_id": "<sid>", "frame_id": N,
   "pass_through": ""}` until `finish_reason` or `next_frame_id <= 0`.

### 3.4 `yuanbao_search_web`

General web search via `tab=all | gov | media`.

**Input**

| Field | Type | Default | Rules |
|---|---|---|---|
| `query` | `str` | — | Required; no explicit length cap |
| `limit` | `int` | `10` | 1–20 |
| `scope` | `"all" \| "gov" \| "media"` | `"all"` | Maps to tab |
| `sort` | `"relevance" \| "date"` | `"relevance"` | Local sort |
| `days` | `int \| null` | `null` | >= 1; local filter |

**Output**

```json
{
  "query": "...",
  "scope": "all",
  "count": 10,
  "results": [
    {
      "title": "...",
      "url": "...",
      "source": "腾讯新闻",
      "date": "2026-07-22",
      "snippet": "...",
      "date_unknown": false
    }
  ],
  "related_queries": ["..."],
  "warnings": []
}
```

- No `site` parameter and no Boolean operators; tool description states this
  explicitly.
- `days` filter keeps undated results with `date_unknown=true` and a warning.
- `sort=date`: undated last.
- Cache: 5 minutes.

---

## 4. Shared HTTP layer

- `httpx.AsyncClient`, HTTP/1.1 keep-alive, realistic Chrome UA for
  `so.qq.com`; WeChat mobile UA for `mp.weixin.qq.com` article fetches.
- Cookie jar persists `cuid` for the process lifetime.
- Global rate limiter: minimum 1 second between *search/article* requests.
  Academic summary frame polling uses a 0.1 second interval (or bypasses the
  limiter) so the summary is not artificially slowed.
- Retry: 2 retries on 429 / 5xx / timeout, exponential backoff + jitter;
  honor `Retry-After`.
- Cache: in-memory TTL dictionary; no negative caching.
- Max response size: 15 MB; larger responses are rejected with a clear error.
- Proxy: `YUANBAO_PROXY` passed to `httpx.AsyncClient(proxy=...)`.
- Logging: stderr only; no query/article content at INFO; DEBUG may log
  sanitized request metadata.

---

## 5. Configuration

Environment variables (prefix `YUANBAO_`), `.env` supported.

| Variable | Default | Purpose |
|---|---|---|
| `YUANBAO_TRANSPORT` | `stdio` | `stdio` or `streamable-http` |
| `YUANBAO_HOST` | `127.0.0.1` | HTTP bind host |
| `YUANBAO_PORT` | `8765` | HTTP port |
| `YUANBAO_LOG_LEVEL` | `INFO` | Logging level |
| `YUANBAO_ENABLE_WEIXIN_SEARCH` | `true` | Register weixin search tool |
| `YUANBAO_ENABLE_ARTICLE_READER` | `true` | Register article reader tool |
| `YUANBAO_ENABLE_ACADEMIC_SEARCH` | `true` | Register academic tool |
| `YUANBAO_ENABLE_WEB_SEARCH` | `true` | Register web search tool |
| `YUANBAO_WEIXIN_DEFAULT_LIMIT` | `20` | Default weixin result count |
| `YUANBAO_WEIXIN_MAX_RESULTS` | `28` | Server cap |
| `YUANBAO_WEB_DEFAULT_LIMIT` | `10` | Default web result count |
| `YUANBAO_WEB_MAX_RESULTS` | `20` | Web cap |
| `YUANBAO_ACADEMIC_DEFAULT_LIMIT` | `10` | Default core papers |
| `YUANBAO_ACADEMIC_MAX_PAPERS` | `20` | Core paper cap |
| `YUANBAO_ACADEMIC_SUMMARY_DEFAULT` | `false` | Default for `include_summary` |
| `YUANBAO_ACADEMIC_SUMMARY_TIMEOUT` | `45` | Summary timeout seconds |
| `YUANBAO_ARTICLE_MAX_CHARS` | `20000` | Default article truncation |
| `YUANBAO_REQUEST_TIMEOUT` | `20` | Per-request timeout |
| `YUANBAO_CONNECT_TIMEOUT` | `10` | Connect timeout in seconds |
| `YUANBAO_MAX_RETRIES` | `2` | Retry attempts for 429/5xx/timeouts |
| `YUANBAO_MIN_INTERVAL` | `1.0` | Rate limit seconds |
| `YUANBAO_CACHE_TTL` | `300` | Search cache TTL |
| `YUANBAO_ARTICLE_CACHE_TTL` | `1800` | Article cache TTL |
| `YUANBAO_ACADEMIC_CACHE_TTL` | `600` | Academic cache TTL |
| `YUANBAO_PROXY` | unset | HTTP proxy |
| `YUANBAO_USER_AGENT` | Chrome UA | Override UA |

CLI flags override env for `--transport`, `--host`, `--port`, `--log-level`.

---

## 6. Errors

Anticipated failures raise `mcp.server.mcpserver.exceptions.ToolError` with
English, actionable messages (`isError=true`). No stack traces to clients.

| Category | Message pattern |
|---|---|
| Invalid input | `Invalid query: ...` / `Only mp.weixin.qq.com article URLs are supported.` |
| Upstream blocked | `Yuanbao blocked this request (rate limit or captcha). Try again later or reduce request frequency.` |
| Article blocked/deleted | `Article is unavailable (deleted, restricted, or requires WeChat client).` |
| Parse failure | `Could not parse the upstream page. The site layout may have changed.` |
| Timeout | `Upstream request timed out after Ns. Try again.` |
| Partial academic | Return partial result with `warnings`, not an error. |
| Empty search | Return empty result with a warning, not an error. |

---

## 7. Security and compliance

- `yuanbao_read_weixin_article` accepts only `http(s)://mp.weixin.qq.com/...`;
  reject other hosts (SSRF prevention).
- Follow redirects but verify the final host is `mp.weixin.qq.com`; otherwise
  reject.
- HTTP mode binds `127.0.0.1` by default; warn if `0.0.0.0` is used.
- No authentication in HTTP mode; document as local-only.
- No login, no cookies from the user, no credentials stored.
- README includes:
  - Not affiliated with Tencent.
  - Uses an undocumented public web surface; may break.
  - `so.qq.com/isearch` is disallowed by robots.txt; `mp.weixin.qq.com`
    article pages are not open to general crawlers.
  - Personal research/reading only; do not redistribute article content.
  - Rate-limit recommendations and no warranty.

---

## 8. Testing and CI

### Unit tests (fixtures)

- RSC payload extraction from `tests/fixtures/weixin_search.html`.
- WeChat card parsing: 26 results, fields, highlight stripping.
- Article parsing: title/account/time/content/images, truncation, error page.
- Academic normalization: `sup_list`, `sub_queries`, summary frames,
  dedupe, abstract truncation.
- Web parsing: normal results, related queries, date unknown.
- Config validation, URL validation, date parsing/filtering.

### Mock HTTP tests (`respx`)

- Successful search/article/academic/web calls.
- Empty results.
- 429 / 5xx retry behavior.
- Blocked article page → `ToolError`.
- Academic partial: sub-questions succeed, `get_sup` fails → partial + warning.
- Summary timeout → partial + `summary_truncated`.

### MCP protocol test

- Launch `uv run yuanbao-search-mcp` over stdio.
- `initialize`, `tools/list` returns 4 tools with schemas and annotations.
- Call `yuanbao_read_weixin_article` with an invalid URL → `isError=true`
  without network.
- Optionally call a fixture-backed tool through a test transport.

### Manual smoke

`scripts/smoke_test.py` calls all four tools against the live site and prints
a summary. Not run in CI.

### CI

GitHub Actions: `uv sync --frozen`, `ruff check`, `pytest`. No live network.

---

## 9. Repository layout

```
yuanbao-search-mcp/
├── .github/workflows/ci.yml
├── .gitignore
├── LICENSE
├── README.md                 # English
├── README.zh-CN.md           # Chinese
├── CAPABILITIES.md           # capability investigation report
├── DESIGN.md                 # this document
├── pyproject.toml
├── uv.lock
├── src/yuanbao_search_mcp/
│   ├── __init__.py
│   ├── __main__.py
│   ├── config.py
│   ├── models.py
│   ├── client.py             # httpx client, rate limit, retry, cache
│   ├── parsers.py            # RSC, weixin cards, article, web
│   ├── academic.py           # session, subq, sup, summary frames
│   ├── service.py            # four high-level operations
│   └── server.py             # MCPServer, tool registration, CLI
├── scripts/smoke_test.py
└── tests/
    ├── fixtures/
    ├── test_parsers.py
    ├── test_service.py
    ├── test_config.py
    └── test_mcp_protocol.py
```

---

## 10. Tool annotations and descriptions

All tools are read-only, non-destructive, open-world:

```python
ToolAnnotations(
    title="...",
    read_only_hint=True,
    destructive_hint=False,
    idempotent_hint=False,
    open_world_hint=True,
)
```

Descriptions are English and explicitly state limitations:

- WeChat search: no pagination, max ~28 results, no Boolean/site syntax.
- Article reader: mp.weixin.qq.com only; content belongs to the original author.
- Academic: AI summary is off by default, may be partial; citations map to
  `core_papers[].citation_id`.
- Web search: no `site:` or Boolean operators; local date filtering only.

Server instructions summarize the data source, the four tools, and the
personal-use/compliance caveat.

---

## 11. Open risks

1. Upstream RSC/API structures can change without notice; fixture tests catch
   parser regressions but not live changes.
2. `so.qq.com` launched on 2026-11-11 and is still evolving.
3. Anti-crawl/rate limiting may appear under heavy use.
4. `mp.weixin.qq.com` may require WeChat client for some articles.
5. Academic summary generation can stall; timeout/partial semantics are
   mandatory.
6. No official support; robots.txt restrictions apply.
