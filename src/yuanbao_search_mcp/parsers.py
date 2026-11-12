"""Parsers for Yuanbao search result pages and WeChat article pages."""

from __future__ import annotations

import html as html_lib
import json
import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any
from urllib.parse import urlparse

from .client import UpstreamParseError
from .models import WeixinArticle

_HIGHLIGHT_RE = re.compile(r"[\ue40a\ue40b]")
_TAG_RE = re.compile(r"<[^>]+>")
_CHUNK_RE = re.compile(r'self\.__next_f\.push\(\[1,(".*?")\]\)</script>', re.S)
_DATE_RE = re.compile(r"^(\d{4})[-/](\d{1,2})[-/](\d{1,2})")
_DATE_CN_RE = re.compile(r"^(\d{4})年(\d{1,2})月(\d{1,2})日")
_FIGURE_RE = re.compile(r"<figure\b[^>]*>.*?</figure>", re.S | re.I)

_BLOCK_MARKERS = (
    "环境异常",
    "请输入验证码",
    "访问过于频繁",
    "操作频繁",
    "请在微信客户端打开链接",
)
_ARTICLE_ERROR_MARKERS = (
    "该内容已被发布者删除",
    "此内容因违规无法查看",
    "内容已被删除",
    "参数错误",
)


@dataclass
class ParsedArticle:
    title: str
    account: str | None
    publish_time: str | None
    content: str
    images: list[str] = field(default_factory=list)


def strip_highlight(value: str) -> str:
    return _HIGHLIGHT_RE.sub("", value)


def clean_text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    text = html_lib.unescape(value)
    text = _TAG_RE.sub("", text)
    text = strip_highlight(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text or None


def truncate(text: str | None, limit: int) -> tuple[str | None, bool]:
    if text is None:
        return None, False
    if len(text) <= limit:
        return text, False
    return text[:limit].rstrip(), True


def normalize_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.hostname == "mp.weixin.qq.com" and parsed.scheme == "http":
        return "https://" + url[len("http://") :]
    return url


def parse_date(value: str | None) -> date | None:
    if not value:
        return None
    text = value.strip()
    match = _DATE_RE.search(text) or _DATE_CN_RE.search(text)
    if not match:
        return None
    try:
        return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
    except ValueError:
        return None


def extract_year(value: str | None) -> str | None:
    if not value:
        return None
    match = re.search(r"(?:19|20)\d{2}", value)
    return match.group(0) if match else None


def extract_next_payload(html: str) -> str:
    chunks = _CHUNK_RE.findall(html)
    if not chunks:
        return html
    parts: list[str] = []
    for chunk in chunks:
        try:
            parts.append(json.loads(chunk))
        except json.JSONDecodeError:
            continue
    return "".join(parts)


def _extract_json_object(text: str, start: int) -> dict[str, Any]:
    depth = 0
    in_string = False
    escaped = False
    for index in range(start, len(text)):
        char = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return json.loads(text[start : index + 1])
    raise UpstreamParseError("Unbalanced JSON object in RSC payload")


def extract_initial_cards(html: str) -> list[dict[str, Any]]:
    payload = extract_next_payload(html)
    marker = '{"initialCards":'
    start = payload.find(marker)
    if start < 0:
        marker = '\\"initialCards\\":'
        start = payload.find(marker)
        if start < 0:
            return []
        payload = payload.replace('\\"', '"').replace("\\\\", "\\")
        start = payload.find('{"initialCards":')
        if start < 0:
            return []
    try:
        data = _extract_json_object(payload, start)
    except (json.JSONDecodeError, UpstreamParseError):
        return []
    cards = data.get("initialCards")
    return cards if isinstance(cards, list) else []


def parse_weixin_cards(cards: list[dict[str, Any]]) -> list[WeixinArticle]:
    results: list[WeixinArticle] = []
    seen: set[str] = set()
    for card in cards:
        data = card.get("data") or {}
        vm = data.get("vm") or {}
        if data.get("cardName") != "card-common/card30010612" and not vm.get("isWxmpTab"):
            continue
        title = clean_text(vm.get("title"))
        raw_url = vm.get("jumpUrl")
        if not title or not isinstance(raw_url, str) or not raw_url:
            continue
        url = normalize_url(raw_url)
        doc_id = str(vm.get("docId") or "") or None
        key = doc_id or url
        if key in seen:
            continue
        seen.add(key)
        results.append(
            WeixinArticle(
                title=title,
                account=clean_text(vm.get("authorName")),
                publish_time=clean_text(vm.get("publishTime")),
                summary=clean_text(vm.get("summary")),
                url=url,
                doc_id=doc_id,
                cover_url=vm.get("imgUrl") if isinstance(vm.get("imgUrl"), str) else None,
                date_unknown=parse_date(clean_text(vm.get("publishTime"))) is None,
            )
        )
    return results


def is_blocked_page(html: str) -> bool:
    return any(marker in html for marker in _BLOCK_MARKERS)


def is_article_error_page(html: str) -> bool:
    return any(marker in html for marker in _ARTICLE_ERROR_MARKERS)
