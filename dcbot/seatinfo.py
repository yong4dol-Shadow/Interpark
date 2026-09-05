"""게시글 텍스트에서 좌석 정보(구역/열/번호 등)를 정규식으로 추출한다.

디시인사이드 양도/취켓팅 글은 자유 형식이라 100% 파싱은 불가능하다.
여기서는 "알림에 요약을 덧붙이는" 용도의 가벼운 휴리스틱만 사용한다.
"""

from __future__ import annotations

import re
from typing import Dict, List

# 공백/전각공백 정리를 위한 패턴
_WS_RE = re.compile(r"[\s 　]+")

# 항목별 추출 패턴 (label, compiled regex, formatter)
_PATTERNS = [
    (
        "date",
        re.compile(r"(\d{1,2})\s*월\s*(\d{1,2})\s*일|(\d{1,2})\s*/\s*(\d{1,2})(?!\d)"),
        lambda m: (
            f"{m.group(1)}/{m.group(2)}" if m.group(1) else f"{m.group(3)}/{m.group(4)}"
        ),
    ),
    (
        "grade",
        re.compile(r"\b(VIP|vip|R|S|A|B)\s*석|(스탠딩|플로어|지정석|자유석)"),
        lambda m: (f"{m.group(1).upper()}석" if m.group(1) else m.group(2)),
    ),
    ("floor", re.compile(r"(\d{1,2})\s*층"), lambda m: f"{m.group(1)}층"),
    (
        "zone",
        re.compile(r"([A-Za-z]{1,3}|[가-힣]{1,4}|\d{1,3})\s*(?:구역|블럭|블록|존)"),
        lambda m: f"{m.group(1).upper()}구역",
    ),
    ("row", re.compile(r"(\d{1,3})\s*열"), lambda m: f"{m.group(1)}열"),
    (
        "seat",
        re.compile(r"(\d{1,4})\s*번(?:대)?(?!째|호|길|지|은|을|째로)"),
        lambda m: f"{m.group(1)}번",
    ),
    (
        "count",
        re.compile(r"(\d{1,2})\s*(?:연석|장|매)(?!출)"),
        lambda m: f"{m.group(1)}매",
    ),
    (
        "price",
        re.compile(r"(\d{1,3}(?:,\d{3})+|\d{4,7})\s*원"),
        lambda m: f"{m.group(1)}원",
    ),
]

# 요약에 노출할 순서
_ORDER = ["date", "grade", "floor", "zone", "row", "seat", "count", "price"]

# 항목당 최대 개수 (한 글에 여러 좌석이 적혀 있어도 알림이 길어지지 않도록)
_MAX_PER_LABEL = 3


def normalize(text: str) -> str:
    """연속 공백 제거 등 가벼운 정규화."""
    if not text:
        return ""
    return _WS_RE.sub(" ", text).strip()


def extract_seat_info(text: str) -> Dict[str, List[str]]:
    """텍스트에서 좌석 관련 항목을 라벨별로 추출한다."""
    cleaned = normalize(text)
    if not cleaned:
        return {}

    result: Dict[str, List[str]] = {}
    for label, pattern, formatter in _PATTERNS:
        found: List[str] = []
        for match in pattern.finditer(cleaned):
            try:
                value = formatter(match)
            except (AttributeError, IndexError):  # pragma: no cover - 방어적 처리
                continue
            if value and value not in found:
                found.append(value)
            if len(found) >= _MAX_PER_LABEL:
                break
        if found:
            result[label] = found
    return result


def summarize_seat_info(text: str) -> str:
    """좌석 정보를 알림용 한 줄 요약 문자열로 변환한다.

    예) "8/15 · VIP석 · 2층 · A구역 · 3열 · 12번 · 2매"
    핵심 좌석 정보(구역/열/번호/층)가 전혀 없으면 빈 문자열을 반환한다.
    """
    info = extract_seat_info(text)
    if not info:
        return ""

    # 구역/열/번호/층 중 하나도 없으면 좌석 글로 보지 않는다.
    if not any(key in info for key in ("zone", "row", "seat", "floor")):
        return ""

    parts: List[str] = []
    for label in _ORDER:
        values = info.get(label)
        if values:
            parts.append(" ".join(values))
    return " · ".join(parts)
