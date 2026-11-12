# yuanbao-search-mcp

[English](README.md) | [简体中文](README.zh-CN.md)

腾讯元宝搜索 MCP 服务：微信公众号文章搜索、学术搜索和通用网页搜索。

## 为什么需要这个项目

腾讯云官方元宝搜索 API（`SearchPro`）出于版权原因明确不包含微信公众号内容。本项目通过 `so.qq.com` 的公开网页入口补齐这一能力。本项目与腾讯无关，上游页面可能随时变化，恕不另行通知。

## 工具

| 工具 | 功能 |
|---|---|
| `yuanbao_search_weixin_articles` | 搜索微信公众号文章 |
| `yuanbao_read_weixin_article` | 读取微信公众号文章的标题和正文 |
| `yuanbao_search_academic` | 搜索核心论文、子问题，可选生成 AI 总结 |
| `yuanbao_search_web` | 搜索全部 / 政府 / 主流媒体结果 |

四个工具均为只读、返回结构化结果，并同时支持 stdio 和 Streamable HTTP。

## 安装

需要 Python 3.11+ 和 [uv](https://docs.astral.sh/uv/)。请将 `<your-repo-url>` 替换为本仓库的克隆地址。

```bash
git clone <your-repo-url> yuanbao-search-mcp
cd yuanbao-search-mcp
uv sync
```

### pip / pipx 备用安装方式

本项目未发布到 PyPI，请从本地克隆安装。请在已激活的虚拟环境中运行 pip 命令（pipx 会自动创建虚拟环境）。

```bash
python -m pip install .
yuanbao-search-mcp
```

或使用 [pipx](https://pipx.pypa.io/)：

```bash
pipx install .
yuanbao-search-mcp
```

## 运行

stdio（默认）：

```bash
uv run yuanbao-search-mcp
```

Streamable HTTP：

```bash
uv run yuanbao-search-mcp --transport streamable-http --port 8765
# endpoint: http://127.0.0.1:8765/mcp
```

HTTP 传输默认绑定 `127.0.0.1`，且没有身份认证。请仅在本机使用。命令行参数 `--transport`、`--host`、`--port`、`--log-level` 会覆盖对应的环境变量。

## 客户端配置

请将 `/absolute/path/to/yuanbao-search-mcp` 替换为克隆目录的绝对路径（可在目录内运行 `pwd` 获取）。修改客户端配置后请重启客户端。

### OpenCode

在 `~/.config/opencode/opencode.jsonc` 中添加：

```json
{
  "mcp": {
    "yuanbao-search": {
      "type": "local",
      "command": [
        "uv",
        "run",
        "--directory",
        "/absolute/path/to/yuanbao-search-mcp",
        "yuanbao-search-mcp"
      ],
      "enabled": true
    }
  }
}
```

### Claude Desktop

在 `claude_desktop_config.json` 中添加：

```json
{
  "mcpServers": {
    "yuanbao-search": {
      "command": "uv",
      "args": [
        "run",
        "--directory",
        "/absolute/path/to/yuanbao-search-mcp",
        "yuanbao-search-mcp"
      ]
    }
  }
}
```

### Cursor / VS Code

Cursor（`~/.cursor/mcp.json`）：

```json
{
  "mcpServers": {
    "yuanbao-search": {
      "command": "uv",
      "args": [
        "run",
        "--directory",
        "/absolute/path/to/yuanbao-search-mcp",
        "yuanbao-search-mcp"
      ]
    }
  }
}
```

VS Code（`.vscode/mcp.json`）：

```json
{
  "servers": {
    "yuanbao-search": {
      "type": "stdio",
      "command": "uv",
      "args": [
        "run",
        "--directory",
        "/absolute/path/to/yuanbao-search-mcp",
        "yuanbao-search-mcp"
      ]
    }
  }
}
```

也可以使用相同的 stdio 命令，或在启动 HTTP 模式后将客户端指向 `http://127.0.0.1:8765/mcp`。

### Claude Code

```bash
claude mcp add yuanbao-search -- uv run --directory /absolute/path/to/yuanbao-search-mcp yuanbao-search-mcp
```

## 工具参考

### `yuanbao_search_weixin_articles`

搜索元宝收录的微信公众号文章。

| 参数 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `query` | 字符串 | `""` | 搜索关键词。提供 `account` 时可以留空；`query` 与 `account` 至少提供一个。 |
| `account` | 字符串或 null | `null` | 仅保留账号名包含该字符串的结果。大小写不敏感的本地后置过滤。 |
| `limit` | 整数 | `20` | 1–28；超出范围会按服务端上限截断。 |
| `sort` | `"relevance"` 或 `"date"` | `"relevance"` | `date` 按发布时间从新到旧排序；无日期的结果排在最后。 |
| `days` | 整数或 null | `null` | 仅保留最近 N 个自然日（含今天）的文章，N >= 1。本地过滤。 |

返回：

```json
{
  "query": "大模型",
  "account": null,
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

`total_available` 是应用 `limit` 之前的本地匹配数量，并非上游总数。上游每次查询大约返回 26–28 篇文章，且没有分页。上游搜索不支持布尔运算符或 `site:`。

### `yuanbao_read_weixin_article`

读取微信公众号文章，返回标题和正文。

| 参数 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `url` | 字符串 | — | 必填。必须是 `mp.weixin.qq.com` 上的 `http(s)` URL。 |
| `max_chars` | 整数 | `20000` | 1,000–100,000；超出范围会截断。优先在段落边界截断。 |

返回：

```json
{
  "title": "...",
  "account": "...",
  "publish_time": "2026-11-12",
  "url": "https://mp.weixin.qq.com/s?...",
  "content": "Lightweight Markdown body",
  "char_count": 5303,
  "original_chars": 5303,
  "truncated": false,
  "images": ["https://mmbiz.qpic.cn/..."],
  "image_count": 52
}
```

`content` 是轻量 Markdown（段落、标题、列表、引用块）。`images` 最多包含 50 个正文图片 URL；`image_count` 是实际找到的图片总数。文章已删除、受限或只能在微信客户端打开时，工具会返回错误。

### `yuanbao_search_academic`

搜索学术论文。结果包括核心论文、子问题，以及可选的 AI 生成的文献综述。

| 参数 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `query` | 字符串 | — | 必填。研究问题或关键词。 |
| `limit` | 整数 | `10` | 核心论文数量，1–20。不影响子问题论文数量。 |
| `include_summary` | 布尔值 | `false` | 是否生成 AI 学术总结。 |
| `summary_timeout` | 数字 | `45` | 总结超时时间（秒），5–120。 |
| `include_subquestions` | 布尔值 | `true` | 是否包含最多 8 个子问题，每个子问题最多 4 篇论文。 |

返回：

```json
{
  "query": "retrieval augmented generation",
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

核心论文摘要上限为 1,200 字符，子问题论文摘要上限为 300 字符。每篇核心论文最多附带两条证据引文（每条 300 字符）。AI 总结默认关闭，实时生成，可能只返回部分内容：超时时会返回已有内容，并设置 `summary_truncated=true` 和一条警告。总结中的引用标记 `[n,m]` 分别对应 `core_papers[].citation_id` 和 `evidence[].quote_number`。如果核心论文获取失败但子问题成功，结果会部分返回并附带警告；如果两者都失败，工具返回错误。

### `yuanbao_search_web`

通过元宝搜索通用网页。

| 参数 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `query` | 字符串 | — | 必填。关键词或自然语言查询。 |
| `limit` | 整数 | `10` | 1–20；超出范围会按服务端上限截断。 |
| `scope` | `"all"`、`"gov"` 或 `"media"` | `"all"` | 全部结果、政府结果或主流媒体结果。 |
| `sort` | `"relevance"` 或 `"date"` | `"relevance"` | `date` 按日期从新到旧排序；无日期的结果排在最后。 |
| `days` | 整数或 null | `null` | 仅保留最近 N 个自然日（含今天）的结果，N >= 1。本地过滤。 |

返回：

```json
{
  "query": "人工智能",
  "scope": "all",
  "count": 10,
  "results": [
    {
      "title": "...",
      "url": "https://...",
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

上游搜索不支持 `site:`、`filetype:`、布尔运算符或其他高级搜索语法；请按自然语言查询处理，多个词之间是隐式 AND 关系。

## 配置

将 `config.example.env` 复制为 `.env`，或在客户端的 `env` 配置块中设置 `YUANBAO_*` 环境变量。下表列出全部支持的变量；设计说明见 `DESIGN.md`。

| 变量 | 默认值 | 用途 |
|---|---|---|
| `YUANBAO_TRANSPORT` | `stdio` | `stdio` 或 `streamable-http` |
| `YUANBAO_HOST` | `127.0.0.1` | HTTP 绑定地址 |
| `YUANBAO_PORT` | `8765` | HTTP 端口 |
| `YUANBAO_LOG_LEVEL` | `INFO` | 日志级别 |
| `YUANBAO_ENABLE_WEIXIN_SEARCH` | `true` | 注册公众号搜索工具 |
| `YUANBAO_ENABLE_ARTICLE_READER` | `true` | 注册文章阅读工具 |
| `YUANBAO_ENABLE_ACADEMIC_SEARCH` | `true` | 注册学术搜索工具 |
| `YUANBAO_ENABLE_WEB_SEARCH` | `true` | 注册网页搜索工具 |
| `YUANBAO_WEIXIN_DEFAULT_LIMIT` | `20` | 公众号搜索默认结果数 |
| `YUANBAO_WEIXIN_MAX_RESULTS` | `28` | 公众号搜索服务端上限 |
| `YUANBAO_WEB_DEFAULT_LIMIT` | `10` | 网页搜索默认结果数 |
| `YUANBAO_WEB_MAX_RESULTS` | `20` | 网页搜索上限 |
| `YUANBAO_ACADEMIC_DEFAULT_LIMIT` | `10` | 学术核心论文默认数量 |
| `YUANBAO_ACADEMIC_MAX_PAPERS` | `20` | 核心论文上限 |
| `YUANBAO_ACADEMIC_SUMMARY_DEFAULT` | `false` | `include_summary` 的默认值 |
| `YUANBAO_ACADEMIC_SUMMARY_TIMEOUT` | `45` | 总结超时时间（秒） |
| `YUANBAO_ARTICLE_MAX_CHARS` | `20000` | 文章截断默认字符数 |
| `YUANBAO_REQUEST_TIMEOUT` | `20` | 单次请求超时时间 |
| `YUANBAO_CONNECT_TIMEOUT` | `10` | 连接超时时间（秒） |
| `YUANBAO_MAX_RETRIES` | `2` | 429/5xx/超时的重试次数 |
| `YUANBAO_MIN_INTERVAL` | `1.0` | 限速间隔（秒） |
| `YUANBAO_CACHE_TTL` | `300` | 搜索缓存 TTL |
| `YUANBAO_ARTICLE_CACHE_TTL` | `1800` | 文章缓存 TTL |
| `YUANBAO_ACADEMIC_CACHE_TTL` | `600` | 学术搜索缓存 TTL |
| `YUANBAO_PROXY` | 未设置 | HTTP 代理 |
| `YUANBAO_USER_AGENT` | Chrome UA | 覆盖 User-Agent |

`.env` 从服务器进程的工作目录读取。默认的 `uv run --directory ...` 启动方式会使用项目根目录，因此放在根目录的 `.env` 会被加载。

## 工具说明与限制

- 公众号搜索每次大约返回 26–28 条结果，且没有分页。
- 公众号账号过滤使用大小写不敏感的“包含”匹配和本地后置过滤，无法保证返回某个账号的全部文章。
- `days` 是本地过滤；无日期的结果会保留，并标记 `date_unknown=true`。
- 公众号文章阅读仅支持 `mp.weixin.qq.com` URL。
- 学术 AI 总结默认关闭，且可能只返回部分内容。
- 网页搜索不支持 `site:` 或布尔运算符。
- 需要按时间倒序时使用 `sort=date`；无日期的结果排在最后。
- 响应会在内存中缓存：搜索 5 分钟、文章 30 分钟、学术搜索 10 分钟。相同的重复调用可能返回缓存数据。
- 默认请求限速为每秒一次，并对 429、5xx 和超时响应进行重试。

v0.1.0 不包含：AI 模式问答、视频搜索、图片搜索、阅读数/点赞/评论、学术图表或思维导图，以及历史记录、收藏等需要登录的功能。

## 合规说明

本项目是个人研究/阅读工具，与腾讯无关。`so.qq.com/robots.txt` 禁止抓取 `so.qq.com/isearch`，`mp.weixin.qq.com` 的文章页也不对通用爬虫开放。请勿将本项目用于高频抓取、转载文章内容或商业用途。上游数据归原作者和发布方所有。本项目按现状提供，不附带任何担保。

## 故障排查

- **提示 `uv: command not found`** — 请从 <https://docs.astral.sh/uv/getting-started/installation/> 安装 uv。
- **客户端中没有出现这些工具** — 检查对应的 `YUANBAO_ENABLE_*` 变量，确认同一命令可以在终端启动，然后重启客户端。
- **图形界面客户端无法启动服务器** — GUI 应用可能不会继承 shell 的 `PATH`。请在客户端配置中使用 `uv` 的绝对路径（运行 `which uv` 查看）。
- **出现 `Yuanbao blocked this request`** — 降低请求频率、稍后重试，或通过 `YUANBAO_PROXY` 走代理。内置限速为每秒一次请求。
- **出现 `Article is unavailable`** — 文章已被删除、受限，或需要在微信客户端中打开。请在微信中打开链接确认。
- **学术总结过短或缺失** — 总结生成可能卡住。请增大 `summary_timeout`，或关闭 `include_summary`。检查 `warnings` 和 `summary_truncated`。
- **HTTP 模式无法连接** — 确认服务器已启动、端口一致，且 URL 以 `/mcp` 结尾。如果端口被占用，请换一个 `--port`。
- **需要更多日志** — 设置 `YUANBAO_LOG_LEVEL=DEBUG`。日志输出到 stderr，不会破坏 stdio MCP 通信。

## 开发

```bash
uv sync
uv run ruff check .
uv run pytest -q
uv run python scripts/smoke_test.py
```

冒烟测试会调用线上服务，不包含在 CI 中。

## 许可证

代码采用 MIT 许可证。文章和搜索内容归原始来源所有。
