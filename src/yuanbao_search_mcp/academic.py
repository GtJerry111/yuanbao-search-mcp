"""Academic search session and response parsing."""

from __future__ import annotations

import asyncio
import re
import time
from typing import Any
from urllib.parse import quote

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
            url = doc.get("url")
            if not title or not isinstance(url, str) or not url:
                continue
            key = title.casefold()
            if key in seen:
                continue
            seen.add(key)
            abstract, _ = truncate(
                clean_text(doc.get("abstract_short") or doc.get("abstract")), 300
            )
            papers.append(
                AcademicDoc(
                    title=title,
                    venue=clean_text(doc.get("journal_name")) or clean_text(doc.get("show_name")),
                    year=str(doc["year"])
                    if doc.get("year") is not None
                    else extract_year(doc.get("publication_date")),
                    url=url,
                    abstract_short=abstract,
                )
            )
        result.append(AcademicSubQuestion(question=question, papers=papers[:4]))
    return result


def parse_summary_frame(payload: dict[str, Any]) -> tuple[str, int | None, bool]:
    data = payload.get("data") or {}
    steps = data.get("steps") or []
    text = "\n".join(
        step.get("step_text", "")
        for step in steps
        if isinstance(step, dict) and step.get("step_text")
    )
    next_frame = data.get("next_frame_id")
    if not isinstance(next_frame, int):
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
            remaining = max(0.5, deadline - time.monotonic())
            try:
                payload = await self._client.post_json(
                    FRAME_URL,
                    {"session_id": self.session_id, "frame_id": frame, "pass_through": ""},
                    headers=self._headers(),
                    rate_limit=False,
                    timeout=min(remaining, 30.0),
                )
            except UpstreamTimeoutError:
                truncated = True
                break
            except UpstreamError:
                truncated = True
                break

            _check_payload(payload)
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
                break
            frame = next_frame
            if poll_interval > 0:
                await asyncio.sleep(poll_interval)
        else:
            truncated = True

        summary = "\n\n".join(chunks)
        return summary, truncated, len(summary), figures_omitted
