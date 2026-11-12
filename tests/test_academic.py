import json
from pathlib import Path

from yuanbao_search_mcp.academic import (
    extract_session_id,
    parse_sub_questions,
    parse_summary_frame,
    parse_sup,
)

FIXTURES = Path(__file__).parent / "fixtures"


def test_extract_session_id() -> None:
    html = (FIXTURES / "academic_search.html").read_text(encoding="utf-8")
    session_id = extract_session_id(html)
    assert len(session_id) == 36
    assert session_id.count("-") == 4


def test_parse_sup() -> None:
    payload = json.loads((FIXTURES / "academic_sup.json").read_text(encoding="utf-8"))
    papers = parse_sup(payload)
    assert len(papers) == 18
    assert papers[0].citation_id == 1
    assert papers[0].title
    assert papers[0].authors
    assert papers[0].year
    assert len(papers[0].evidence) == 2


def test_parse_sub_questions() -> None:
    payload = json.loads((FIXTURES / "academic_subq.json").read_text(encoding="utf-8"))
    sub_questions = parse_sub_questions(payload)
    assert len(sub_questions) == 8
    assert all(0 < len(question.papers) <= 4 for question in sub_questions)
    assert len(sub_questions[0].papers) == 4
    assert all(
        len({paper.title for paper in question.papers}) == len(question.papers)
        for question in sub_questions
    )
    assert sub_questions[0].question
    assert sub_questions[0].papers[0].title


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
