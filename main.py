#!/usr/bin/env python3
"""디시인사이드 갤러리 모니터링 봇 실행 진입점.

사용 예)
    python main.py                # 무한 루프 실행
    python main.py --once         # 한 사이클만 실행(테스트용)
    python main.py --dry-run      # 알림 대신 콘솔 출력
    python main.py --test-notify  # 알림 채널 연결 테스트
"""

from __future__ import annotations

import argparse
import logging
import os
import sys

from dcbot.bot import MonitorBot
from dcbot.config import Config
from dcbot.health import start_health_server
from dcbot.logging_setup import setup_logging
from dcbot.models import Detection, Post
from dcbot.notifier import build_notifier

logger = logging.getLogger("dcbot.main")


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="디시인사이드 갤러리 키워드 모니터링 봇")
    parser.add_argument("--env", default=None, help=".env 파일 경로 (기본: ./.env)")
    parser.add_argument("--once", action="store_true", help="한 사이클만 실행하고 종료")
    parser.add_argument("--dry-run", action="store_true", help="실제 알림 대신 콘솔 출력")
    parser.add_argument(
        "--test-notify", action="store_true", help="샘플 알림을 1건 보내고 종료"
    )
    return parser.parse_args(argv)


def send_test_notification(config: Config) -> int:
    notifier = build_notifier(config)
    post = Post(
        no=999999,
        title="[테스트] 취켓팅 성공 / A구역 3열 12번 2연석 양도합니다",
        url=config.post_url(999999),
        writer="테스트봇",
        created_at="테스트",
        body="테스트 본문입니다. VIP석 2층 A구역 3열 12번 2연석, 정가 양도합니다.",
    )
    detection = Detection(
        post=post,
        matched_keywords=["취켓팅", "양도"],
        seat_summary="VIP석 · 2층 · A구역 · 3열 · 12번 · 2매",
    )
    ok = notifier.send(detection, config)
    logger.info("테스트 알림 전송 %s", "성공" if ok else "실패")
    return 0 if ok else 1


def main(argv=None) -> int:
    args = parse_args(argv)
    if args.dry_run:
        # 설정 검증 전에 반영해야 알림 채널 미설정 오류를 피할 수 있다.
        os.environ["DRY_RUN"] = "true"
    try:
        config = Config.from_env(args.env)
    except ValueError as exc:
        # 설정 오류는 스택트레이스 없이 명확히 알린다.
        setup_logging("INFO")
        logger.error("설정 오류: %s", exc)
        return 2

    setup_logging(config.log_level)

    if args.test_notify:
        return send_test_notification(config)

    bot = MonitorBot(config)
    if args.once:
        try:
            detections = bot.run_once()
            logger.info("단발 실행 완료: 감지 %d건", len(detections))
            return 0
        except Exception as exc:
            logger.error("실행 실패: %s", exc)
            return 1
        finally:
            bot.shutdown()

    # Cloud Run 처럼 포트 리스닝이 필요한 환경 대응 (PORT 가 있을 때만 동작)
    start_health_server(
        lambda: {
            "status": "ok",
            "gallery": config.gallery_id,
            "last_no": bot.state.last_no,
            "keywords": config.keywords,
        }
    )

    bot.run_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
