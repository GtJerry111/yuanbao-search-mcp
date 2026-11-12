"""Pydantic models returned by MCP tools."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class WeixinArticle(BaseModel):
    title: str
    account: str | None = None
    publish_time: str | None = None
    summary: str | None = None
    url: str
    doc_id: str | None = None
    cover_url: str | None = None
    date_unknown: bool = False


class WeixinSearchResult(BaseModel):
    query: str
    account: str | None = None
    count: int
    total_available: int
    results: list[WeixinArticle] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ArticleResult(BaseModel):
    title: str
    account: str | None = None
    publish_time: str | None = None
    url: str
    content: str
    char_count: int
    original_chars: int
    truncated: bool
    images: list[str] = Field(default_factory=list)
    image_count: int = 0


class AcademicEvidence(BaseModel):
    quote_number: int
    quote: str


class AcademicPaper(BaseModel):
    citation_id: int | None = None
    title: str
    authors: list[str] = Field(default_factory=list)
    venue: str | None = None
    year: str | None = None
    cited_by: int | None = None
    url: str | None = None
    abstract: str | None = None
    abstract_truncated: bool = False
    evidence: list[AcademicEvidence] = Field(default_factory=list)


class AcademicDoc(BaseModel):
    title: str
    venue: str | None = None
    year: str | None = None
    url: str | None = None
    abstract_short: str | None = None


class AcademicSubQuestion(BaseModel):
    question: str
    papers: list[AcademicDoc] = Field(default_factory=list)


class AcademicSearchResult(BaseModel):
    query: str
    core_papers: list[AcademicPaper] = Field(default_factory=list)
    sub_questions: list[AcademicSubQuestion] = Field(default_factory=list)
    summary: str | None = None
    summary_truncated: bool = False
    summary_char_count: int = 0
    warnings: list[str] = Field(default_factory=list)


class WebResult(BaseModel):
    title: str
    url: str
    source: str | None = None
    date: str | None = None
    snippet: str | None = None
    date_unknown: bool = False


class WebSearchResult(BaseModel):
    query: str
    scope: Literal["all", "gov", "media"]
    count: int
    results: list[WebResult] = Field(default_factory=list)
    related_queries: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
