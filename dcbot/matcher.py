"""키워드 매칭 로직."""

from __future__ import annotations

import re
from typing import Iterable, List

_WS_RE = re.compile(r"\s+")


def _normalize(text: str) -> str:
    """공백/대소문자 차이를 무시하기 위한 정규화.

    '취 켓 팅' 처럼 필터 회피용으로 공백을 끼워 넣는 글도 잡기 위해 공백을 제거한다.
    """
    return _WS_RE.sub("", text or "").lower()


class KeywordMatcher:
    def __init__(
        self, keywords: Iterable[str], exclude_keywords: Iterable[str] = ()
    ) -> None:
        self.keywords = [k for k in keywords if k]
        self.exclude_keywords = [k for k in exclude_keywords if k]
        self._normalized = [(k, _normalize(k)) for k in self.keywords]
        self._normalized_exclude = [_normalize(k) for k in self.exclude_keywords]

    def match(self, text: str) -> List[str]:
        """포함된 키워드 목록을 돌려준다. 제외 키워드가 걸리면 빈 리스트."""
        target = _normalize(text)
        if not target:
            return []
        if any(ex and ex in target for ex in self._normalized_exclude):
            return []
        return [original for original, norm in self._normalized if norm and norm in target]
