"""도메인 데이터 모델."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class Post:
    """갤러리 게시글 1건."""

    no: int
    title: str
    url: str
    writer: str = ""
    created_at: str = ""
    reply_count: int = 0
    view_count: int = 0
    body: Optional[str] = None

    @property
    def haystack(self) -> str:
        """키워드 매칭 대상 텍스트(제목 + 본문)."""
        return f"{self.title}\n{self.body or ''}"


@dataclass
class Detection:
    """키워드가 감지된 게시글과 부가 분석 결과."""

    post: Post
    matched_keywords: List[str] = field(default_factory=list)
    seat_summary: str = ""
    matched_in_body: bool = False
