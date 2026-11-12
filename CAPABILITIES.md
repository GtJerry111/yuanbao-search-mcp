# 元宝搜索（so.qq.com）能力探查报告

> 探查时间：2026-11-12
> 目的：在决定 MCP 封装范围前，确认各能力的入口、字段、限制、稳定性和合规风险。
> 结论：公众号搜索/正文、学术科普（论文+可选 AI 总结）、AI 模式问答、通用网页、视频均可获取；但公众号只能走非官方网页解析，官方 API 明确不含公众号。

---

## 1. 能力矩阵

| 能力 | 入口 | 返回内容 | 登录 | 实测延迟 | 稳定性 | 建议 |
|---|---|---|---|---|---|---|
| 公众号搜索 | `/isearch?query=...&tab=weixin_article` | 约 28 条：标题、公众号、发布日期、摘要、原文链接、docId、封面 | 否 | 1–2s | 中高 | **封装（核心）** |
| 公众号正文 | `mp.weixin.qq.com/s?...` | 标题、公众号、发布时间、全文、图片 URL | 否 | 1–3s | 中 | **封装（核心）** |
| 学术科普-论文 | `tab=xueshu` + `search_for_subq` / `frame_get` | 8 个子问题、约 36 篇论文、3–18 篇核心文献（作者/期刊/年份/引用数/摘要/DOI/证据引文） | 否 | 8–12s | 中 | **封装** |
| 学术科普-AI 总结 | `academic_agent/frame_get` 逐帧 | 约 3,000–5,000 字综述，带 `[n,m]` 引用 | 否 | 20–60s，可能卡住 | 低-中 | 可选，默认关 |
| AI 模式问答 | `/iaimode/search` 的 SSE | 生成答案、引用来源、追问建议 | 否 | 10–15s | 中（需浏览器/签名） | 可选 |
| 通用网页搜索 | `tab=all` / `gov` / `media` | 标题、URL、摘要、来源、日期；富卡片含图片/翻译 | 否 | 1–2s | 高 | 可选/低优先 |
| 视频搜索 | `tab=weixin_video` | 时长、标题、账号、发布时间 | 否 | 1–3s + 客户端渲染 | 中 | 可选 |
| 图片搜索 | `tab=pic` | 视觉网格；当前 SSR 回退成网页结果 | 否 | — | 低 | 不建议 |
| 相关搜索 | 结果页 hint 卡 | 8–30 个相关词 | 否 | 随搜索 | 高 | 可附带 |
| 时间筛选 | 页面「时间」下拉 | 当前 headless 页面未稳定出现；`tsn/sort/time` 参数无效 | 否 | — | 低 | 不做，改本地按日期过滤 |
| 分页 | `&page=2` | 无效；公众号固定约 28 条 | 否 | — | — | 不做 |
| 阅读数/点赞/评论 | 文章页 JS | 不可靠，部分需登录 | 部分 | — | 低 | 不做 |
| 搜索历史/收藏 | 登录态 | 需登录 | 是 | — | — | 不做 |
| 学术图表/思维导图 | `figures` 字段 | 未稳定返回 | 否 | — | 低 | 不做 |

---

## 2. 公众号搜索（核心）

**入口**

```
GET https://so.qq.com/isearch?query=<urlencoded>&tab=weixin_article
```

**返回结构**

页面是 Next.js RSC 渲染，结果藏在 `self.__next_f.push([1,"..."])` 的 payload 里，`initialCards` 数组中每个 `card-common/card30010612` 就是一条：

```json
{
  "title": "面向真实世界的商业运营和工业制造的递归自进化(RSI)",
  "summary": "本文探讨递归自我改进（RSI）如何从经典组合优化走向真实商业运营与工业制造场景……",
  "authorName": "词元潮汐",
  "publishTime": "2026-11-09",
  "docId": "17088597819742059542",
  "host": "http://mp.weixin.qq.com",
  "imgUrl": "https://mmbiz.qpic.cn/...",
  "jumpUrl": "http://mp.weixin.qq.com/s?__biz=...&mid=...&idx=1&sn=...#rd"
}
```

**实测**

- 单次约 28 条，无服务端分页；`page=2/3` 返回相同结果。
- 查询词高亮用私有字符 `\ue40a` / `\ue40b` 包裹，输出前需要清洗。
- 结果按相关性排序；日期范围可能很广（实测 2026-06 到 2026-11）。
- URL 参数 `tsn=1/2/3/4`、`sort=time`、`sort_type=1`、`time=1/week/month` 均无效。
- 连续 5 次无间隔请求（不同 query）均返回 200，未触发验证码；但不代表可以高频调用。
- 搜索公众号名：`量子位` 返回 29 条，其中 20 条来自「量子位」、5 条来自「量子位智库」；混入关键词后精度下降（`量子位 大模型` 只有 9/29 来自「量子位」）。
- 结论：**“指定公众号内搜索”不能依赖服务端过滤**，需要先按账号名搜，再本地按 `authorName` 过滤；或搜关键词后本地过滤账号。

**限制**

- 无分页，最多约 28 条。
- 无稳定时间筛选；只能本地按 `publishTime` 过滤。
- 结果页是 RSC 结构，字段位置可能随改版变化。
- 受 robots.txt 限制：`so.qq.com` 仅允许 `/` 和 `/ihome`，`/isearch` 为 Disallow。

---

## 3. 公众号正文（核心）

**入口**

```
GET <jumpUrl>   // http(s)://mp.weixin.qq.com/s?__biz=...&mid=...&idx=...&sn=...&chksm=...&rd
```

**可提取字段**

- `#activity-name`：标题
- `#js_name`：公众号名称
- `#publish_time`：发布时间
- `#js_content`：正文
- `#js_content img[data-src]`：正文图片 URL

**实测**

- 一篇 2026 大模型盘点文章：页面 3.7 MB，正文 5,303 字，标题/公众号/时间完整。
- 正文图片：52 个 `data-src`，21 个 `<img>`，可提取。
- 阅读数/点赞数：页面有 `read_num` 等 JS 变量，但没有稳定的服务端渲染值，且可能需要登录/微信客户端；不建议封装。
- 评论：JS 异步加载，未发现可直接调用的公开接口。
- 删文/参数错误：返回约 31 KB 的错误页，含「参数错误」「该内容已被发布者删除」「此内容因违规无法查看」等文案，可检测。
- 部分文章可能要求微信客户端或触发环境异常，需要错误提示和重试策略。

**限制**

- `mp.weixin.qq.com` 的文章页对通用爬虫是 Disallow（robots.txt）。
- 正文版权归原作者/公众号所有；MCP 适合个人阅读/总结，不适合公开再分发。
- 图片 URL 有防盗链/时效性，不一定能长期直接访问。

---

## 4. 学术科普（重点）

**入口**

1. 打开 `https://so.qq.com/isearch?query=<q>&tab=xueshu`，从 RSC payload 提取 `sessionId`（UUID）。
2. 并行调用两个内部接口：
   - `POST https://lizhiassistant.search.qq.com/vertical_hub/academic/search_for_subq`
     ```json
     {"query": "...", "uuid": "<sessionId>", "guid": "", "session_id": "<sessionId>"}
     ```
   - `POST https://lizhiassistant.search.qq.com/academic_agent/frame_get`
     ```json
     {"session_id": "<sessionId>", "get_sup": 1, "pass_through": ""}
     ```
3. 如需 AI 学术总结，继续逐帧拉取：
   ```json
   {"session_id": "...", "frame_id": 0, "pass_through": ""}
   ```
   每帧返回一段 `steps[].step_text`，直到 `finish_reason` 非空或 `next_frame_id <= 0`。

**返回内容**

- `search_for_subq`：通常 8 个子问题，每个 4 篇论文，共约 36 篇；字段包括 `title`、`abstract`、`abstract_short`、`authors`、`year`、`url`、`journal_name`、`publication_date`、`show_name`、`relevance_score`。
- `frame_get (get_sup=1)`：核心文献列表（实测 3–18 篇，随 query 变化）；字段包括 `id`（引用编号）、`title`、`abstract`、`url`、`authors`、`journal_name`、`cited_by_count`、`publication_date`、`evidences[].quote`。
- AI 学术总结：Markdown 风格，含 `[n,m]` 引用（n = 核心文献 id，m = 证据序号），以及 `<figure figure-id="fig-1" figure-type="mind_map"></figure>` 占位；实测 3,000–5,000 字。
- 图表/思维导图：`figures` 字段在多次探测中均为空，`figure_ready=0`；暂不可用。

**实测**

- 页面创建会话约 0.8–1.1s。
- `search_for_subq` 约 7.5s；`get_sup` 约 1.4–7.5s；两者可并行。
- AI 总结逐帧返回，前 30 帧约 1,400–2,000 字，速度约 0.15–0.5s/帧；第 30 帧后可能长时间卡住（30s 超时），需要超时返回部分内容。
- 支持中英文 query；论文来源包括 arXiv、ACL、IEEE、ACM、ScienceDirect、Consensus、科普中国等。

**限制**

- 内部接口无公开文档，`sessionId` 由页面生成，接口可能随版本变化。
- AI 总结是实时生成，可能很慢或中途停住；必须设置超时并允许部分结果。
- `get_sup` 返回的文献数量不稳定，不能假设固定 10 篇。
- 论文链接多为 DOI/摘要页，不保证有可直接下载的 PDF。

---

## 5. AI 模式问答

**入口**

```
GET https://so.qq.com/iaimode/search?query=<urlencoded>
```

页面会带 `sid` 并流式请求：

```
POST https://lizhiassistant.search.qq.com/browser_aimode/aimode/query_get
```

请求体包含 `session_id`、`uid`、`query`、`model: "deepseek-v3"`、`verify`（salt/timestamp/sign）、`uskey` 等；其中签名/风控参数由页面 JS 生成，**不能直接用 HTTP 重放**。

**SSE 事件**

- `anti_crawl`：风控结果
- `query_info`：query_id / trace_id
- `search_info`：`search_results[]`，含 `index`、`title`、`url`、`abstract`、`site_name`、`time`
- `chat.completion.chunk`：答案 token，含 `[citation:N]`
- `afu`：追问建议（如“上海未来三天天气预报”）

**实测**

- 免登录可用；答案约 10–15s 完成。
- 答案带引用编号，可映射到 `search_info.search_results`。
- 需要 Playwright/真实浏览器执行页面 JS；直接 HTTP 重放签名请求不可行。

**限制**

- 依赖浏览器（Chromium + Playwright），体积/启动成本高。
- 页面结构和签名逻辑可能随时变化。
- 生成答案有事实错误风险，引用来源需保留。

---

## 6. 通用网页 / 视频 / 图片

### 通用网页

- `tab=all`：普通结果卡约 6–13 条 + 富卡片（`card30010588` 带图/翻译，`card30010608` 公众号文章卡）+ 相关搜索。
- `tab=gov` / `tab=media`：按政府/主流媒体过滤，返回普通结果卡。
- 字段：`title`、`url`、`host`、`content`、`sourcename`、`date`、`favicon`、`imageUrl` 等。
- 稳定、快，但官方腾讯云 API 也能覆盖（不含公众号），优先级较低。

### 视频

- `tab=weixin_video`：SSR 返回 0 卡，内容客户端渲染。
- 用 Playwright 可拿到 16+ 条：时长、标题、账号、发布时间（如“6天前”）。
- 没有直接可用的视频文件 URL；主要是视频号内容展示。
- 需要浏览器，优先级中等。

### 图片

- `tab=pic`：当前 SSR 返回与 `all` 相同的网页结果，未看到稳定图片网格数据。
- 不建议封装。

---

## 6.5 搜索语法支持（重要）

实测结论：**不支持布尔式，也不支持 `site:`。** 它更像自然语言/多词隐式 AND 搜索。

| 语法 | 实测结果 | 结论 |
|---|---|---|
| `site:zhihu.com 人工智能` | 0 条 | 不支持 |
| `site:qq.com` / `site:github.com` / `site:mp.weixin.qq.com` | 均 0 条 | 不支持 |
| `src:` / `domain:` / `host:` / `来源:` | 被当成普通关键词，结果不是限定站点 | 不支持 |
| `filetype:pdf` | 被当成普通关键词 | 不支持 |
| `人工智能 -大模型` | 10 条，结果仍大量包含“大模型” | `-` 不生效 |
| `人工智能 NOT 大模型` | 11 条，仍包含“大模型” | `NOT` 不生效 |
| `苹果 OR 香蕉` | 13 条，全是“苹果和香蕉”同时出现的内容；与单独搜“苹果”“香蕉”零重叠 | `OR` 不生效，默认隐式 AND |
| `苹果 \| 香蕉` / `苹果 + 香蕉` | 同上，仍是同时包含 | 不生效 |
| `"人工智能"` vs `人工智能` | 结果集仅 2/11 重叠 | 引号会影响排序，但不是严格精确短语，不可依赖 |
| `intitle:"人工智能"` | 未强制标题包含 | 不生效 |

**对 MCP 的影响：**

- 不要在工具描述里承诺布尔语法或 `site:` 过滤。
- `account`、`days`、按域名过滤都只能做**客户端后置过滤**，召回受服务端结果限制。
- 如果确实需要站内搜索，优先建议使用腾讯云 `SearchPro` 的 `Site` 参数（需 API Key，且不含公众号）。
- 公众号的 `account` 参数只能“搜账号名 + 本地严格匹配 `authorName`”，不能保证穷尽该账号所有文章。

---

## 7. 官方能力对比（重要）

腾讯云有正式的「元宝搜索」API：

- 产品：`SearchPro`（`wsa.tencentcloudapi.com` / `api.wsa.cloud.tencent.com`）
- 官方 MCP：`https://api.wsa.cloud.tencent.com/Mcp`，一个工具 `SearchPro`，Streamable HTTP + Bearer API Key
- 支持：`Query`、`Site`、`Mode`、`Cnt`（10/20/30/40/50）、`Industry`（gov/news/acad/finance）、`Freshness`（dN/mN/yN/日期区间）、`Deeplinks`
- 延迟：平均 600–800ms；QPS：极速/标准 20，旗舰 5
- **明确限制：由于内容版权问题，官方元宝搜索 API 暂不支持微信公众号内容。**

结论：

- **公众号搜索/正文**：官方 API 不提供，只能走 `so.qq.com` / `mp.weixin.qq.com` 网页解析。这正是自建 MCP 的独特价值。
- **通用网页/学术**：官方 API 可作为更稳定、合规的替代或补充；如果用户有腾讯云 API Key，可以把它作为可选后端。
- **AI 总结/问答**：官方 API 不提供生成式答案；需要自建或接其他 LLM。

---

## 8. 风险与限制

1. **robots.txt**：`so.qq.com` 仅允许 `/` 和 `/ihome`；`/isearch` 被 Disallow。`mp.weixin.qq.com` 文章页也不允许通用爬虫。自用可以，但不建议对外分发、商用或高频抓取。
2. **版权**：公众号正文归原作者/公众号所有；MCP 输出应限于个人阅读、检索、总结，不应公开再分发。
3. **非官方接口**：RSC 结构、学术内部 API、AI 模式签名都可能随版本变化；需要容错和清晰的错误提示。
4. **频率风控**：实测 5 次连续请求未触发验证码，但不代表安全；建议 1 req/s + 缓存 + 重试退避。
5. **稳定性分层**：
   - 高：通用网页、相关搜索
   - 中高：公众号搜索
   - 中：公众号正文、学术论文、AI 模式
   - 低-中：学术 AI 总结
   - 低：图片、时间筛选、阅读数/评论、学术图表

---

## 9. 建议的封装菜单（供拍板）

| 方案 | 包含能力 | 价值 | 成本/风险 | 适合 |
|---|---|---|---|---|
| A | 公众号搜索 + 正文 | 最高；官方 API 没有 | 中；需解析 RSC + 反爬处理 | 以公众号检索为核心 |
| B | A + 学术科普（论文 + 可选 AI 总结） | 高；学术调研 | 中高；内部 API + 超时控制 | 研究/内容创作 |
| C | B + AI 模式问答 | 高；直接给答案+引用 | 高；需 Playwright | 想要“搜索+总结”一站式 |
| D | C + 通用网页/视频 | 全覆盖 | 高；维护面大 | 做通用搜索 MCP |
| E | 只做学术科普 | 中高；比公众号更“干净” | 中 | 学术场景为主 |

**默认建议**：先做 A，确认公众号搜索/正文的稳定性；如果学术是刚需，再加 B。AI 模式和通用网页可以后置，避免第一版背上浏览器和更多反爬面。

---

## 10. 待你拍板的问题

1. 是否接受“非官方网页解析”作为公众号能力的实现方式？（官方 API 明确不含公众号）
2. 是否需要学术科普？AI 总结是否默认关闭？（此前已确认默认关闭）
3. 是否需要 AI 模式问答？这会把 Playwright 变成硬依赖。
4. 通用网页/视频是否要？如果只是公众号+学术，可以不做。
5. 使用范围：个人自用 / 团队内部 / 对外分发？这决定限速、缓存和合规策略。
