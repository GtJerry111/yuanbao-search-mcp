"""Academic search session and response parsing."""

from __future__ import annotations

import asyncio
import re
import time
from typing import Any
from urllib.parse import quote, urlparse

from .client import (
    HttpClient,
    UpstreamBlockedError,
    UpstreamError,
    UpstreamParseError,
    UpstreamTimeoutError,
)
from .models import AcademicDoc, AcademicEvidence, AcademicPaper, AcademicSubQuestion
from .parsers import (
    _FIGURE_RE,
    clean_text,
    extract_year,
    is_blocked_page,
    truncate,
)

_SESSION_RE = re.compile(r'sessionId\\?"\s*:\s*\\?"([0-9a-f-]{36})', re.I)
_UUID_RE = re.compile(r'uuid\\?"\s*:\s*\\?"([0-9a-f-]{36})', re.I)
_ARXIV_PATH_RE = re.compile(r"(?:abs|pdf|html)/(.+?)(?:\.pdf)?$", re.I)
_ARXIV_VERSION_RE = re.compile(r"v\d+$", re.I)
_DOI_RE = re.compile(r"10\.\d{4,9}/[^\s?#]+")

ACADEMIC_PAGE = "https://so.qq.com/isearch"
SUBQ_URL = "https://lizhiassistant.search.qq.com/vertical_hub/academic/search_for_subq"
FRAME_URL = "https://lizhiassistant.search.qq.com/academic_agent/frame_get"


def extract_session_id(html: str) -> str:
    match = _SESSION_RE.search(html) or _UUID_RE.search(html)
    if not match:
        raise UpstreamParseError("Could not create an academic session")
    return match.group(1)


def _check_payload(payload: dict[str, Any]) -> None:
    code = payload.get("code")
    if code not in (None, 0):
        raise UpstreamError(f"Academic API error {code}: {payload.get('msg') or 'unknown'}")
    status = payload.get("status")
    if isinstance(status, dict) and status.get("code") not in (None, 0):
        raise UpstreamError(
            f"Academic API error {status.get('code')}: {status.get('msg') or 'unknown'}"
        )
    data = payload.get("data")
    if isinstance(data, dict) and data.get("code") not in (None, 0):
        raise UpstreamError(
            f"Academic API error {data.get('code')}: {data.get('msg') or 'unknown'}"
        )


def _normalized_url_key(url: str | None) -> str | None:
    if not url:
        return None
    parsed = urlparse(url.strip())
    host = (parsed.hostname or "").lower()
    if not host:
        return None
    if host.startswith("www."):
        host = host[4:]
    path = parsed.path.rstrip("/")
    query = f"?{parsed.query}" if parsed.query else ""
    return f"{host}{path}{query}"


def _dedupe_keys(title: str, url: str | None) -> set[str]:
    keys = {f"title:{title.casefold()}"}
    if not url:
        return keys
    normalized = _normalized_url_key(url)
    if normalized is None:
        return keys
    keys.add(f"url:{normalized}")
    parsed = urlparse(url.strip())
    host = (parsed.hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    path = parsed.path.rstrip("/")
    if host == "arxiv.org":
        match = _ARXIV_PATH_RE.match(path.lstrip("/"))
        if match:
            ident = _ARXIV_VERSION_RE.sub("", match.group(1))
            if ident:
                keys.add(f"arxiv:{ident.lower()}")
    doi_match = _DOI_RE.search(parsed.path or url)
    if doi_match:
        doi = doi_match.group(0).rstrip(".,;)]").lower()
        if doi:
            keys.add(f"doi:{doi}")
    return keys


def _sub_question_year(doc: dict[str, Any]) -> str | None:
    year = doc.get("year")
    if isinstance(year, bool):
        year = None
    if isinstance(year, int):
        if year > 0:
            return str(year)
    elif isinstance(year, str):
        text = year.strip()
        if text.isdigit() and int(text) > 0:
            return text
    publication_date = doc.get("publication_date")
    return extract_year(publication_date if isinstance(publication_date, str) else None)


def parse_sup(payload: dict[str, Any]) -> list[AcademicPaper]:
    items = ((payload.get("data") or {}).get("sup_list")) or []
    papers: list[AcademicPaper] = []
    seen: set[str] = set()
    for item in items:
        title = clean_text(item.get("title"))
        if not title:
            continue
        key = title.casefold()
        if key in seen:
            continue
        seen.add(key)
        authors = item.get("authors") or []
        if isinstance(authors, str):
            authors = [authors]
        authors = [author for author in (clean_text(value) for value in authors) if author]

        evidence: list[AcademicEvidence] = []
        for entry in (item.get("evidences") or [])[:2]:
            quote = clean_text(entry.get("quote"))
            if not quote:
                continue
            evidence.append(
                AcademicEvidence(
                    quote_number=int(entry.get("quote_number") or len(evidence) + 1),
                    quote=truncate(quote, 300)[0] or "",
                )
            )

        abstract, abstract_truncated = truncate(clean_text(item.get("abstract")), 1200)
        papers.append(
            AcademicPaper(
                citation_id=int(item["id"]) if item.get("id") is not None else None,
                title=title,
                authors=authors,
                venue=clean_text(item.get("journal_name")),
                year=extract_year(item.get("publication_date")),
                cited_by=int(item["cited_by_count"])
                if item.get("cited_by_count") is not None
                else None,
                url=item.get("url") if isinstance(item.get("url"), str) else None,
                abstract=abstract,
                abstract_truncated=abstract_truncated,
                evidence=evidence,
            )
        )
    return papers


def parse_sub_questions(payload: dict[str, Any]) -> list[AcademicSubQuestion]:
    items = ((payload.get("data") or {}).get("sub_queries")) or []
    result: list[AcademicSubQuestion] = []
    for item in items:
        question = clean_text(item.get("display_title") or item.get("query"))
        if not question:
            continue
        papers: list[AcademicDoc] = []
        seen: set[str] = set()
        for doc in item.get("docs") or []:
            title = clean_text(doc.get("title"))
            if not title:
                continue
            raw_url = doc.get("url")
            url = raw_url.strip() if isinstance(raw_url, str) and raw_url.strip() else None
            if url is None:
                continue
            keys = _dedupe_keys(title, url)
            if keys & seen:
                continue
            seen.update(keys)
            abstract, _ = truncate(
                clean_text(doc.get("abstract_short") or doc.get("abstract")), 300
            )
            papers.append(
                AcademicDoc(
                    title=title,
                    venue=clean_text(doc.get("journal_name")) or clean_text(doc.get("show_name")),
                    year=_sub_question_year(doc),
                    url=url,
                    abstract_short=abstract,
                )
            )
        result.append(AcademicSubQuestion(question=question, papers=papers[:4]))
    return result[:8]


def parse_summary_frame(payload: dict[str, Any]) -> tuple[str, int | None, bool]:
    data = payload.get("data") or {}
    steps = data.get("steps") or []
    text = "\n".join(
        step.get("step_text", "")
        for step in steps
        if isinstance(step, dict) and step.get("step_text")
    )
    next_frame = data.get("next_frame_id")
    if isinstance(next_frame, bool) or not isinstance(next_frame, int):
        next_frame = None
    finished = bool(data.get("finish_reason")) or next_frame is None or next_frame <= 0
    return text, next_frame, finished


class AcademicSession:
    def __init__(self, client: HttpClient, query: str) -> None:
        self._client = client
        self.query = query
        self.session_id = ""
        self.page_url = f"{ACADEMIC_PAGE}?query={quote(query)}&tab=xueshu"

    def _headers(self) -> dict[str, str]:
        return {
            "origin": "https://so.qq.com",
            "referer": self.page_url,
            "accept": "application/json, text/plain, */*",
            "content-type": "application/json",
        }

    async def create(self) -> str:
        html = await self._client.get(
            ACADEMIC_PAGE,
            params={"query": self.query, "tab": "xueshu"},
        )
        if is_blocked_page(html):
            raise UpstreamBlockedError("Yuanbao returned an anti-crawl page")
        self.session_id = extract_session_id(html)
        return self.session_id

    async def fetch_sub_questions(self) -> list[AcademicSubQuestion]:
        payload = await self._client.post_json(
            SUBQ_URL,
            {
                "query": self.query,
                "uuid": self.session_id,
                "guid": "",
                "session_id": self.session_id,
            },
            headers=self._headers(),
        )
        _check_payload(payload)
        return parse_sub_questions(payload)

    async def fetch_sup(self) -> list[AcademicPaper]:
        payload = await self._client.post_json(
            FRAME_URL,
            {"session_id": self.session_id, "get_sup": 1, "pass_through": ""},
            headers=self._headers(),
            timeout=60.0,
        )
        _check_payload(payload)
        return parse_sup(payload)

    async def fetch_summary(
        self,
        timeout: float,
        poll_interval: float = 0.1,
    ) -> tuple[str, bool, int, bool]:
        deadline = time.monotonic() + timeout
        frame = 0
        chunks: list[str] = []
        truncated = False
        figures_omitted = False

        while time.monotonic() < deadline:
            remaining = max(0.01, deadline - time.monotonic())
            try:
                payload = await asyncio.wait_for(
                    self._client.post_json(
                        FRAME_URL,
                        {"session_id": self.session_id, "frame_id": frame, "pass_through": ""},
                        headers=self._headers(),
                        rate_limit=False,
                        timeout=min(remaining, 30.0),
                    ),
                    timeout=remaining,
                )
                _check_payload(payload)
            except (UpstreamTimeoutError, TimeoutError, UpstreamError):
                truncated = True
                break

            text, next_frame, finished = parse_summary_frame(payload)
            if text:
                if _FIGURE_RE.search(text):
                    figures_omitted = True
                text = _FIGURE_RE.sub("", text).strip()
                if text:
                    chunks.append(text)
            if finished:
                break
            if next_frame is None or next_frame <= frame:
                truncated = True
                break
            frame = next_frame
            if poll_interval > 0:
                sleep_for = max(0.0, min(poll_interval, deadline - time.monotonic()))
                if sleep_for > 0:
                    await asyncio.sleep(sleep_for)
        else:
            truncated = True

        summary = "\n\n".join(chunks)
        return summary, truncated, len(summary), figures_omitted
