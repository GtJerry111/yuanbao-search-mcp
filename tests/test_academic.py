import asyncio
import json
import time
from pathlib import Path
from typing import Any

import pytest

from yuanbao_search_mcp.academic import (
    AcademicSession,
    _check_payload,
    extract_session_id,
    parse_sub_questions,
    parse_summary_frame,
    parse_sup,
)
from yuanbao_search_mcp.client import UpstreamError, UpstreamParseError

FIXTURES = Path(__file__).parent / "fixtures"


class FakeSummaryClient:
    def __init__(self, responses: list[dict[str, Any]]) -> None:
        self._responses = responses
        self.calls = 0

    async def post_json(self, url: str, payload: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
        response = self._responses[min(self.calls, len(self._responses) - 1)]
        self.calls += 1
        return response


class SlowSummaryClient:
    async def post_json(self, url: str, payload: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
        await asyncio.sleep(0.5)
        return {"data": {}}


def test_extract_session_id() -> None:
    html = (FIXTURES / "academic_search.html").read_text(encoding="utf-8")
    session_id = extract_session_id(html)
    assert len(session_id) == 36
    assert session_id.count("-") == 4


def test_extract_session_id_uuid_fallback() -> None:
    html = '{"uuid":"aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"}'
    assert extract_session_id(html) == "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"


def test_extract_session_id_missing_raises() -> None:
    with pytest.raises(UpstreamParseError):
        extract_session_id("<html></html>")


def test_parse_sup() -> None:
    payload = json.loads((FIXTURES / "academic_sup.json").read_text(encoding="utf-8"))
    papers = parse_sup(payload)
    assert len(papers) == 18
    assert papers[0].citation_id == 1
    assert papers[0].title
    assert papers[0].authors
    assert papers[0].year
    assert len(papers[0].evidence) == 2


def test_parse_sup_truncates_abstract_and_evidence() -> None:
    payload = {
        "data": {
            "sup_list": [
                {
                    "id": 1,
                    "title": "Long Paper",
                    "authors": ["A. Author"],
                    "abstract": "A" * 1300,
                    "evidences": [{"quote_number": 1, "quote": "Q" * 400}],
                }
            ]
        }
    }
    paper = parse_sup(payload)[0]
    assert paper.abstract_truncated is True
    assert paper.abstract is not None
    assert len(paper.abstract) == 1200
    assert len(paper.evidence[0].quote) == 300


def test_parse_sup_empty_authors_and_metadata() -> None:
    payload = {
        "data": {
            "sup_list": [
                {
                    "id": 9,
                    "title": "Mapped Paper",
                    "authors": None,
                    "journal_name": "Journal of Tests",
                    "publication_date": "2023-04",
                    "cited_by_count": 12,
                    "url": "https://example.com/paper",
                    "evidences": [],
                }
            ]
        }
    }
    paper = parse_sup(payload)[0]
    assert paper.authors == []
    assert paper.venue == "Journal of Tests"
    assert paper.year == "2023"
    assert paper.url == "https://example.com/paper"
    assert paper.cited_by == 12


def test_parse_sub_questions() -> None:
    payload = json.loads((FIXTURES / "academic_subq.json").read_text(encoding="utf-8"))
    sub_questions = parse_sub_questions(payload)
    assert len(sub_questions) == 8
    for question in sub_questions:
        assert 1 <= len(question.papers) <= 4
        titles = [paper.title for paper in question.papers]
        assert len(set(titles)) == len(titles)
        urls = [paper.url for paper in question.papers if paper.url is not None]
        assert len(set(urls)) == len(urls)
    assert sub_questions[0].question
    assert sub_questions[0].papers[0].title


def test_parse_sub_questions_year_sentinel() -> None:
    payload = {
        "data": {
            "sub_queries": [
                {
                    "query": "q",
                    "docs": [
                        {
                            "title": "Dated Paper",
                            "url": "https://example.com/dated",
                            "year": 0,
                            "publication_date": "2024-05",
                        },
                        {
                            "title": "Undated Paper",
                            "url": "https://example.com/undated",
                            "year": 0,
                        },
                    ],
                }
            ]
        }
    }
    papers = parse_sub_questions(payload)[0].papers
    assert papers[0].year == "2024"
    assert papers[1].year is None


def test_parse_sub_questions_dedupes_arxiv_variants() -> None:
    payload = {
        "data": {
            "sub_queries": [
                {
                    "query": "q",
                    "docs": [
                        {
                            "title": "Variant One",
                            "url": "https://arxiv.org/html/2406.14319v1",
                        },
                        {
                            "title": "Variant Two",
                            "url": "https://arxiv.org/pdf/2406.14319v1",
                        },
                    ],
                }
            ]
        }
    }
    papers = parse_sub_questions(payload)[0].papers
    assert len(papers) == 1
    assert papers[0].title == "Variant One"


def test_parse_sub_questions_dedupes_arxiv_versions() -> None:
    payload = {
        "data": {
            "sub_queries": [
                {
                    "query": "q",
                    "docs": [
                        {
                            "title": "Versioned Paper",
                            "url": "https://arxiv.org/abs/2609.13166v1",
                        },
                        {
                            "title": "Unversioned Paper",
                            "url": "https://arxiv.org/html/2609.13166",
                        },
                    ],
                }
            ]
        }
    }
    papers = parse_sub_questions(payload)[0].papers
    assert len(papers) == 1
    assert papers[0].title == "Versioned Paper"


def test_parse_sub_questions_dedupes_publisher_dois() -> None:
    payload = {
        "data": {
            "sub_queries": [
                {
                    "query": "q",
                    "docs": [
                        {
                            "title": "Full DOI",
                            "url": "https://dl.acm.org/doi/full/10.1145/3775043.3775047",
                        },
                        {
                            "title": "Bare DOI",
                            "url": "https://dl.acm.org/doi/10.1145/3775043.3775047",
                        },
                        {
                            "title": "Resolver DOI",
                            "url": "https://doi.org/10.1145/3775043.3775047",
                        },
                    ],
                }
            ]
        }
    }
    papers = parse_sub_questions(payload)[0].papers
    assert len(papers) == 1
    assert papers[0].title == "Full DOI"


def test_parse_sub_questions_skips_url_less_docs() -> None:
    payload = {
        "data": {
            "sub_queries": [
                {
                    "query": "q",
                    "docs": [
                        {"title": "Shadowing Paper", "abstract_short": "no url"},
                        {"title": "Shadowing Paper", "url": "https://example.com/paper"},
                    ],
                }
            ]
        }
    }
    papers = parse_sub_questions(payload)[0].papers
    assert len(papers) == 1
    assert papers[0].url == "https://example.com/paper"


def test_parse_sub_questions_truncates_abstract_short() -> None:
    payload = {
        "data": {
            "sub_queries": [
                {
                    "query": "q",
                    "docs": [
                        {
                            "title": "Long Abstract",
                            "url": "https://example.com/long",
                            "abstract_short": "A" * 400,
                        }
                    ],
                }
            ]
        }
    }
    papers = parse_sub_questions(payload)[0].papers
    assert papers[0].abstract_short is not None
    assert len(papers[0].abstract_short) == 300


def test_parse_summary_frame() -> None:
    payload = {
        "data": {
            "steps": [{"step_text": "Part one."}],
            "next_frame_id": 1,
            "finish_reason": "",
            "figures": [],
        }
    }
    text, next_frame, finished = parse_summary_frame(payload)
    assert text == "Part one."
    assert next_frame == 1
    assert finished is False

    final = {
        "data": {
            "steps": [{"step_text": "Part two."}],
            "next_frame_id": -1,
            "finish_reason": "stop",
        }
    }
    text, next_frame, finished = parse_summary_frame(final)
    assert text == "Part two."
    assert finished is True


def test_parse_summary_frame_finish_conditions() -> None:
    text, next_frame, finished = parse_summary_frame(
        {
            "data": {
                "steps": [{"step_text": "Done."}],
                "next_frame_id": 2,
                "finish_reason": "stop",
            }
        }
    )
    assert text == "Done."
    assert next_frame == 2
    assert finished is True

    _, next_frame, finished = parse_summary_frame(
        {"data": {"steps": [{"step_text": "Done."}], "next_frame_id": 0, "finish_reason": ""}}
    )
    assert next_frame == 0
    assert finished is True

    _, next_frame, finished = parse_summary_frame(
        {"data": {"steps": [], "next_frame_id": True, "finish_reason": ""}}
    )
    assert next_frame is None
    assert finished is True


def test_check_payload_errors() -> None:
    for payload in ({"code": 1}, {"status": {"code": 1}}, {"data": {"code": 1}}):
        with pytest.raises(UpstreamError):
            _check_payload(payload)


async def test_fetch_summary_no_progress_sets_truncated() -> None:
    client = FakeSummaryClient(
        [
            {
                "data": {
                    "steps": [{"step_text": "Partial."}],
                    "next_frame_id": 1,
                    "finish_reason": "",
                }
            }
        ]
    )
    session = AcademicSession(client, "q")  # type: ignore[arg-type]
    summary, truncated, _, _ = await session.fetch_summary(timeout=5, poll_interval=0)
    assert "Partial." in summary
    assert truncated is True


async def test_fetch_summary_api_error_preserves_partial() -> None:
    client = FakeSummaryClient(
        [
            {
                "data": {
                    "steps": [{"step_text": "First."}],
                    "next_frame_id": 1,
                    "finish_reason": "",
                }
            },
            {"code": 1, "msg": "err"},
        ]
    )
    session = AcademicSession(client, "q")  # type: ignore[arg-type]
    summary, truncated, _, _ = await session.fetch_summary(timeout=5, poll_interval=0)
    assert "First." in summary
    assert truncated is True


async def test_fetch_summary_hard_timeout() -> None:
    session = AcademicSession(SlowSummaryClient(), "q")  # type: ignore[arg-type]
    started = time.monotonic()
    summary, truncated, _, _ = await session.fetch_summary(timeout=0.1)
    elapsed = time.monotonic() - started
    assert summary == ""
    assert truncated is True
    assert elapsed < 0.4


async def test_fetch_summary_omits_figures() -> None:
    client = FakeSummaryClient(
        [
            {
                "data": {
                    "steps": [{"step_text": '<figure figure-id="fig-1"></figure>Text'}],
                    "next_frame_id": -1,
                    "finish_reason": "stop",
                }
            }
        ]
    )
    session = AcademicSession(client, "q")  # type: ignore[arg-type]
    summary, _, _, figures_omitted = await session.fetch_summary(timeout=5, poll_interval=0)
    assert "Text" in summary
    assert "figure" not in summary
    assert figures_omitted is True


async def test_fetch_summary_finished() -> None:
    client = FakeSummaryClient(
        [
            {
                "data": {
                    "steps": [{"step_text": "Done."}],
                    "next_frame_id": 5,
                    "finish_reason": "stop",
                }
            }
        ]
    )
    session = AcademicSession(client, "q")  # type: ignore[arg-type]
    summary, truncated, _, figures_omitted = await session.fetch_summary(timeout=5, poll_interval=0)
    assert summary == "Done."
    assert truncated is False
    assert figures_omitted is False
