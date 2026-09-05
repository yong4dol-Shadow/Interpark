"""차단 회피용 HTTP 클라이언트.

- 실제 브라우저와 유사한 헤더(User-Agent / Referer / Accept-Language 등) 부착
- User-Agent 로테이션
- 429 / 403 / 5xx 응답과 네트워크 오류에 대한 지수 백오프 재시도
- 요청 사이 최소 간격 보장(랜덤 지터 포함)
"""

from __future__ import annotations

import logging
import random
import time
from typing import Dict, Optional

import requests

logger = logging.getLogger(__name__)

USER_AGENTS = [
    # 데스크톱
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:127.0) Gecko/20100101 Firefox/127.0",
]

MOBILE_USER_AGENTS = [
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Linux; Android 14; SM-S918N) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Mobile Safari/537.36",
]

RETRY_STATUS = {403, 408, 429, 500, 502, 503, 504}


class BlockedError(RuntimeError):
    """디시인사이드가 요청을 차단했다고 판단될 때."""


class HttpClient:
    def __init__(
        self,
        timeout: int = 10,
        max_retries: int = 3,
        max_backoff: float = 300.0,
        min_interval: float = 0.8,
    ) -> None:
        self.timeout = timeout
        self.max_retries = max_retries
        self.max_backoff = max_backoff
        self.min_interval = min_interval
        self._last_request_at = 0.0
        self.session = requests.Session()
        self._user_agent = random.choice(USER_AGENTS)
        self.session.headers.update(self._base_headers(self._user_agent))

    # ------------------------------------------------------------------
    @staticmethod
    def _base_headers(user_agent: str) -> Dict[str, str]:
        return {
            "User-Agent": user_agent,
            "Accept": (
                "text/html,application/xhtml+xml,application/xml;q=0.9,"
                "image/avif,image/webp,*/*;q=0.8"
            ),
            "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
            # brotli 의존성 없이 안전하게 처리하기 위해 gzip/deflate 만 요청한다.
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "same-origin",
            "Sec-Fetch-User": "?1",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
        }

    def rotate_user_agent(self, mobile: bool = False) -> None:
        """User-Agent 를 교체하고 세션 쿠키를 초기화한다."""
        pool = MOBILE_USER_AGENTS if mobile else USER_AGENTS
        self._user_agent = random.choice(pool)
        self.session.cookies.clear()
        self.session.headers.update(self._base_headers(self._user_agent))
        logger.debug("User-Agent 교체: %s", self._user_agent)

    # ------------------------------------------------------------------
    def _throttle(self) -> None:
        """요청 사이 최소 간격 + 랜덤 지터."""
        elapsed = time.monotonic() - self._last_request_at
        wait = self.min_interval + random.uniform(0.0, 0.6) - elapsed
        if wait > 0:
            time.sleep(wait)

    def get(
        self,
        url: str,
        *,
        params: Optional[Dict[str, object]] = None,
        referer: Optional[str] = None,
        mobile: bool = False,
    ) -> requests.Response:
        """GET 요청. 실패 시 지수 백오프로 재시도하고, 끝내 실패하면 예외를 던진다."""
        headers: Dict[str, str] = {}
        if referer:
            headers["Referer"] = referer
        if mobile:
            headers["User-Agent"] = random.choice(MOBILE_USER_AGENTS)

        last_error: Optional[Exception] = None
        for attempt in range(self.max_retries + 1):
            self._throttle()
            try:
                response = self.session.get(
                    url,
                    params=params,
                    headers=headers or None,
                    timeout=self.timeout,
                    allow_redirects=True,
                )
                self._last_request_at = time.monotonic()

                if response.status_code == 200:
                    # 디시인사이드는 차단 시 200 과 함께 안내 페이지를 주기도 한다.
                    if self._looks_blocked(response.text):
                        raise BlockedError("차단 안내 페이지가 반환되었습니다.")
                    return response

                if response.status_code in RETRY_STATUS:
                    last_error = BlockedError(f"HTTP {response.status_code}")
                    logger.warning(
                        "HTTP %s (%s) - 재시도 %s/%s",
                        response.status_code,
                        url,
                        attempt + 1,
                        self.max_retries + 1,
                    )
                    self.rotate_user_agent(mobile=mobile)
                else:
                    response.raise_for_status()
                    return response
            except (requests.RequestException, BlockedError) as exc:
                self._last_request_at = time.monotonic()
                last_error = exc
                logger.warning(
                    "요청 실패(%s): %s - 재시도 %s/%s",
                    url,
                    exc,
                    attempt + 1,
                    self.max_retries + 1,
                )

            if attempt < self.max_retries:
                backoff = min(self.max_backoff, (2**attempt) * 2.0)
                time.sleep(backoff + random.uniform(0.0, 1.5))

        raise BlockedError(f"요청에 반복 실패했습니다: {url} ({last_error})")

    # ------------------------------------------------------------------
    @staticmethod
    def _looks_blocked(html: str) -> bool:
        if not html:
            return True
        markers = (
            "일시적으로 이용이 제한",
            "비정상적인 접근",
            "자동입력 방지",
            "IP가 차단",
            "접속이 차단",
        )
        head = html[:4000]
        return any(marker in head for marker in markers)

    def close(self) -> None:
        self.session.close()
