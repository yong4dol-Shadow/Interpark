"""모니터링 봇 메인 루프."""

from __future__ import annotations

import logging
import random
import signal
import time
from typing import Dict, List, Optional

from .config import Config
from .matcher import KeywordMatcher
from .models import Detection, Post
from .notifier import MultiNotifier, build_notifier
from .scraper import DcinsideScraper
from .seatinfo import summarize_seat_info
from .state import StateStore

logger = logging.getLogger(__name__)


class MonitorBot:
    def __init__(
        self,
        config: Config,
        scraper: Optional[DcinsideScraper] = None,
        notifier: Optional[MultiNotifier] = None,
        state: Optional[StateStore] = None,
    ) -> None:
        self.config = config
        self.scraper = scraper or DcinsideScraper(config)
        self.notifier = notifier or build_notifier(config)
        self.state = state or StateStore(config.state_file, config.seen_history_size)
        self.matcher = KeywordMatcher(config.keywords, config.exclude_keywords)
        self._running = True
        self._cycle = 0

    # ------------------------------------------------------------------
    # 루프
    # ------------------------------------------------------------------
    def install_signal_handlers(self) -> None:
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                signal.signal(sig, self._handle_signal)
            except (ValueError, OSError):  # pragma: no cover - 메인 스레드가 아닐 때
                pass

    def _handle_signal(self, signum, _frame) -> None:  # pragma: no cover
        logger.info("종료 신호(%s) 수신. 현재 사이클을 마치고 종료합니다.", signum)
        self._running = False

    def run_forever(self) -> None:
        """24시간 구동용 무한 루프."""
        self.install_signal_handlers()
        logger.info(
            "모니터링 시작 | 갤러리=%s | 키워드=%s | 주기=%.1f~%.1f초",
            self.config.gallery_id,
            ", ".join(self.config.keywords),
            self.config.poll_min_seconds,
            self.config.poll_max_seconds,
        )

        consecutive_failures = 0
        while self._running:
            try:
                detections = self.run_once()
                consecutive_failures = 0
                if detections:
                    logger.info("이번 사이클 알림 %d건", len(detections))
            except KeyboardInterrupt:  # pragma: no cover
                break
            except Exception as exc:
                consecutive_failures += 1
                backoff = min(
                    self.config.max_backoff_seconds,
                    5.0 * (2 ** min(consecutive_failures - 1, 6)),
                )
                logger.exception(
                    "사이클 실패(%d회 연속): %s → %.0f초 후 재시도",
                    consecutive_failures,
                    exc,
                    backoff,
                )
                # 차단 의심 시 User-Agent 교체 후 길게 쉬어간다.
                self.scraper.client.rotate_user_agent()
                self._sleep(backoff)
                continue

            self._sleep(
                random.uniform(self.config.poll_min_seconds, self.config.poll_max_seconds)
            )

        self.shutdown()

    def _sleep(self, seconds: float) -> None:
        """종료 신호에 빠르게 반응하기 위해 잘게 나눠서 대기한다."""
        deadline = time.monotonic() + seconds
        while self._running and time.monotonic() < deadline:
            time.sleep(min(0.5, max(0.0, deadline - time.monotonic())))

    def shutdown(self) -> None:
        self.state.save()
        self.scraper.close()
        logger.info("모니터링 종료. 상태 저장 완료(last_no=%s)", self.state.last_no)

    # ------------------------------------------------------------------
    # 한 사이클
    # ------------------------------------------------------------------
    def run_once(self) -> List[Detection]:
        self._cycle += 1
        posts = self._collect_posts()
        if not posts:
            logger.warning("리스트에서 글을 가져오지 못했습니다.")
            return []

        new_posts = sorted(
            (p for p in posts if self.state.is_new(p.no)), key=lambda p: p.no
        )
        if not new_posts:
            logger.debug("사이클 %d: 새 글 없음(last_no=%s)", self._cycle, self.state.last_no)
            return []

        # 최초 실행: 과거 글로 알림 폭탄을 맞지 않도록 기준점만 잡는다.
        if self.state.is_first_run and not self.config.notify_on_first_run:
            self.state.update_last_no(p.no for p in new_posts)
            self.state.save()
            logger.info(
                "최초 실행: 기존 글 %d건을 기준점으로 저장했습니다(last_no=%s).",
                len(new_posts),
                self.state.last_no,
            )
            return []

        logger.info("새 글 %d건 확인 중 (최신 번호 %s)", len(new_posts), new_posts[-1].no)

        detections: List[Detection] = []
        processed_nos: List[int] = []
        body_budget = (
            self.config.max_body_fetch_per_cycle if self.config.fetch_body else 0
        )

        for post in new_posts:
            title_hits = self.matcher.match(post.title)

            need_body = self.config.fetch_body
            if need_body and body_budget <= 0:
                # 본문 확인 예산 소진 → 남은 글은 다음 사이클에서 다시 본다.
                logger.info("본문 조회 예산 소진. 글번호 %s 이후는 다음 사이클로 미룹니다.", post.no)
                break

            if need_body:
                body_budget -= 1
                post.body = self.scraper.fetch_body(post) or None
                self._sleep(
                    random.uniform(
                        self.config.body_fetch_delay_min, self.config.body_fetch_delay_max
                    )
                )

            hits = self.matcher.match(post.haystack) if post.body else title_hits

            if not hits:
                processed_nos.append(post.no)
                continue

            detection = Detection(
                post=post,
                matched_keywords=hits,
                seat_summary=summarize_seat_info(post.haystack),
                matched_in_body=bool(post.body) and not title_hits,
            )
            if not self._notify(detection):
                # 알림 실패 → last_no 를 진행시키지 않아 다음 사이클에 재시도한다.
                break

            processed_nos.append(post.no)
            detections.append(detection)

        self.state.update_last_no(processed_nos)
        self.state.save()
        return detections

    # ------------------------------------------------------------------
    def _collect_posts(self) -> List[Post]:
        """설정된 페이지 수만큼 리스트를 모아 글번호 기준으로 중복 제거."""
        merged: Dict[int, Post] = {}
        for page in range(1, self.config.list_pages + 1):
            for post in self.scraper.fetch_list(page):
                merged.setdefault(post.no, post)
        return list(merged.values())

    def _notify(self, detection: Detection) -> bool:
        post = detection.post
        logger.info(
            "🚨 감지: [%s] %s (no=%s, 좌석=%s)",
            ",".join(detection.matched_keywords),
            post.title,
            post.no,
            detection.seat_summary or "-",
        )
        if self.notifier.send(detection, self.config):
            self.state.mark_notified(post.no)
            return True
        logger.error("알림 전송에 모두 실패했습니다(no=%s). 다음 사이클에 재시도합니다.", post.no)
        return False
