"""환경 변수(.env) 로딩 및 설정 객체."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from dotenv import load_dotenv

# 기본 키워드 (환경 변수 KEYWORDS 로 덮어쓸 수 있음)
DEFAULT_KEYWORDS = ["취소", "취켓팅", "양도", "풀림"]


def _split_csv(raw: Optional[str]) -> List[str]:
    if not raw:
        return []
    return [item.strip() for item in raw.split(",") if item.strip()]


def _get_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() in ("1", "true", "yes", "y", "on")


def _get_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    try:
        return int(str(raw).strip())
    except (TypeError, ValueError):
        return default


def _get_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    try:
        return float(str(raw).strip())
    except (TypeError, ValueError):
        return default


@dataclass
class Config:
    """봇 실행에 필요한 모든 설정값."""

    # --- 감시 대상 ---
    gallery_id: str = "vaundy0606"
    gallery_type: str = "mgallery"  # board(정식) | mgallery(마이너) | mini(미니)
    keywords: List[str] = field(default_factory=lambda: list(DEFAULT_KEYWORDS))
    exclude_keywords: List[str] = field(default_factory=list)
    list_pages: int = 1  # 매 사이클마다 확인할 리스트 페이지 수

    # --- 알림 채널 ---
    discord_webhook_url: Optional[str] = None
    telegram_bot_token: Optional[str] = None
    telegram_chat_id: Optional[str] = None

    # --- 예매 링크 ---
    interpark_booking_url: str = "https://tickets.interpark.com/"
    interpark_goods_code: Optional[str] = None

    # --- 크롤링 정책 (IP 차단 방어) ---
    poll_min_seconds: float = 3.0
    poll_max_seconds: float = 7.0
    request_timeout: int = 10
    max_backoff_seconds: float = 300.0
    fetch_body: bool = True
    max_body_fetch_per_cycle: int = 5
    body_fetch_delay_min: float = 1.0
    body_fetch_delay_max: float = 2.5

    # --- 상태 캐시 ---
    state_file: Path = Path("state/last_seen.json")
    seen_history_size: int = 500
    notify_on_first_run: bool = False  # 최초 실행 시 과거 글 알림 여부

    # --- 기타 ---
    log_level: str = "INFO"
    dry_run: bool = False

    # ------------------------------------------------------------------
    @classmethod
    def from_env(cls, dotenv_path: Optional[str] = None) -> "Config":
        """`.env` 파일과 OS 환경 변수를 읽어 Config 를 생성한다."""
        load_dotenv(dotenv_path=dotenv_path, override=False)

        keywords = _split_csv(os.getenv("KEYWORDS")) or list(DEFAULT_KEYWORDS)

        goods_code = (os.getenv("INTERPARK_GOODS_CODE") or "").strip() or None
        booking_url = (os.getenv("INTERPARK_BOOKING_URL") or "").strip()
        if not booking_url:
            booking_url = (
                f"https://tickets.interpark.com/goods/{goods_code}"
                if goods_code
                else "https://tickets.interpark.com/"
            )

        cfg = cls(
            gallery_id=(os.getenv("GALLERY_ID") or "vaundy0606").strip(),
            gallery_type=(os.getenv("GALLERY_TYPE") or "mgallery").strip(),
            keywords=keywords,
            exclude_keywords=_split_csv(os.getenv("EXCLUDE_KEYWORDS")),
            list_pages=max(1, _get_int("LIST_PAGES", 1)),
            discord_webhook_url=(os.getenv("DISCORD_WEBHOOK_URL") or "").strip() or None,
            telegram_bot_token=(os.getenv("TELEGRAM_BOT_TOKEN") or "").strip() or None,
            telegram_chat_id=(os.getenv("TELEGRAM_CHAT_ID") or "").strip() or None,
            interpark_booking_url=booking_url,
            interpark_goods_code=goods_code,
            poll_min_seconds=_get_float("POLL_MIN_SECONDS", 3.0),
            poll_max_seconds=_get_float("POLL_MAX_SECONDS", 7.0),
            request_timeout=_get_int("REQUEST_TIMEOUT", 10),
            max_backoff_seconds=_get_float("MAX_BACKOFF_SECONDS", 300.0),
            fetch_body=_get_bool("FETCH_BODY", True),
            max_body_fetch_per_cycle=_get_int("MAX_BODY_FETCH_PER_CYCLE", 5),
            body_fetch_delay_min=_get_float("BODY_FETCH_DELAY_MIN", 1.0),
            body_fetch_delay_max=_get_float("BODY_FETCH_DELAY_MAX", 2.5),
            state_file=Path((os.getenv("STATE_FILE") or "state/last_seen.json").strip()),
            seen_history_size=_get_int("SEEN_HISTORY_SIZE", 500),
            notify_on_first_run=_get_bool("NOTIFY_ON_FIRST_RUN", False),
            log_level=(os.getenv("LOG_LEVEL") or "INFO").strip().upper(),
            dry_run=_get_bool("DRY_RUN", False),
        )
        cfg.validate()
        return cfg

    # ------------------------------------------------------------------
    def validate(self) -> None:
        if not self.gallery_id:
            raise ValueError("GALLERY_ID 가 비어 있습니다.")
        if self.gallery_type not in ("board", "mgallery", "mini"):
            raise ValueError("GALLERY_TYPE 은 board / mgallery / mini 중 하나여야 합니다.")
        if not self.keywords:
            raise ValueError("KEYWORDS 가 비어 있습니다.")
        if self.poll_min_seconds <= 0 or self.poll_max_seconds < self.poll_min_seconds:
            raise ValueError("POLL_MIN_SECONDS / POLL_MAX_SECONDS 설정이 올바르지 않습니다.")
        if not self.dry_run and not self.has_notifier:
            raise ValueError(
                "알림 채널이 없습니다. DISCORD_WEBHOOK_URL 또는 "
                "TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID 를 설정하거나 DRY_RUN=true 로 실행하세요."
            )

    @property
    def has_notifier(self) -> bool:
        return bool(self.discord_webhook_url) or bool(
            self.telegram_bot_token and self.telegram_chat_id
        )

    # --- URL 헬퍼 ---------------------------------------------------
    @property
    def base_url(self) -> str:
        """갤러리 종류에 따른 게시판 베이스 URL."""
        if self.gallery_type == "board":
            return "https://gall.dcinside.com/board"
        return f"https://gall.dcinside.com/{self.gallery_type}/board"

    @property
    def list_url(self) -> str:
        return f"{self.base_url}/lists/"

    @property
    def view_url(self) -> str:
        return f"{self.base_url}/view/"

    @property
    def gallery_url(self) -> str:
        return f"{self.list_url}?id={self.gallery_id}"

    @property
    def mobile_list_url(self) -> str:
        return f"https://m.dcinside.com/board/{self.gallery_id}"

    def post_url(self, post_no: int, page: int = 1) -> str:
        return f"{self.view_url}?id={self.gallery_id}&no={post_no}&page={page}"
