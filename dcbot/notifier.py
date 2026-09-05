"""알림 채널(Discord Webhook / Telegram Bot)."""

from __future__ import annotations

import html
import logging
import time
from typing import List, Optional, Protocol

import requests

from .config import Config
from .models import Detection

logger = logging.getLogger(__name__)

DISCORD_COLOR = 0xE94F37  # 눈에 잘 띄는 붉은 계열


def _truncate(text: str, limit: int) -> str:
    text = text or ""
    return text if len(text) <= limit else text[: limit - 1] + "…"


class Notifier(Protocol):
    name: str

    def send(self, detection: Detection, config: Config) -> bool:  # pragma: no cover
        ...


class DiscordNotifier:
    name = "discord"

    def __init__(self, webhook_url: str, timeout: int = 10) -> None:
        self.webhook_url = webhook_url
        self.timeout = timeout

    def send(self, detection: Detection, config: Config) -> bool:
        post = detection.post
        fields = [
            {
                "name": "🔗 게시글 바로가기",
                "value": f"[디시인사이드에서 열기]({post.url})",
                "inline": False,
            },
            {
                "name": "🎟️ 인터파크 예매하기",
                "value": f"[예매창 열기]({config.interpark_booking_url})",
                "inline": False,
            },
            {
                "name": "🔎 감지 키워드",
                "value": ", ".join(detection.matched_keywords) or "-",
                "inline": True,
            },
        ]
        if detection.seat_summary:
            fields.insert(
                0,
                {
                    "name": "💺 좌석 정보(자동 추출)",
                    "value": _truncate(detection.seat_summary, 1000),
                    "inline": False,
                },
            )

        description_parts: List[str] = []
        if post.body:
            description_parts.append(_truncate(post.body.replace("\n", " "), 300))
        description_parts.append(
            f"작성자: `{post.writer or '-'}` · 글번호: `{post.no}`"
            + (f" · {post.created_at}" if post.created_at else "")
        )

        payload = {
            "username": "DC 티켓 알리미",
            "content": f"🚨 **[{', '.join(detection.matched_keywords)}]** 새 글 감지!",
            "embeds": [
                {
                    "title": _truncate(post.title, 250),
                    "url": post.url,
                    "description": _truncate("\n".join(description_parts), 2000),
                    "color": DISCORD_COLOR,
                    "fields": fields,
                    "footer": {"text": f"{config.gallery_id} 갤러리 모니터링"},
                }
            ],
        }

        return self._post_with_retry(payload)

    def _post_with_retry(self, payload: dict, max_retries: int = 3) -> bool:
        for attempt in range(max_retries):
            try:
                response = requests.post(
                    self.webhook_url, json=payload, timeout=self.timeout
                )
                if response.status_code in (200, 204):
                    return True
                if response.status_code == 429:
                    # Discord 레이트 리밋: retry_after(초) 만큼 대기 후 재시도
                    retry_after = 1.0
                    try:
                        retry_after = float(response.json().get("retry_after", 1.0))
                    except (ValueError, AttributeError, requests.JSONDecodeError):
                        pass
                    logger.warning("Discord 레이트 리밋. %.1f초 대기", retry_after)
                    time.sleep(min(retry_after, 30.0))
                    continue
                logger.error(
                    "Discord 전송 실패: HTTP %s %s",
                    response.status_code,
                    _truncate(response.text, 200),
                )
            except requests.RequestException as exc:
                logger.error("Discord 전송 오류: %s", exc)
            time.sleep(2**attempt)
        return False


class TelegramNotifier:
    name = "telegram"

    def __init__(self, bot_token: str, chat_id: str, timeout: int = 10) -> None:
        self.api_url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        self.chat_id = chat_id
        self.timeout = timeout

    def send(self, detection: Detection, config: Config) -> bool:
        post = detection.post
        esc = html.escape
        lines = [
            f"🚨 <b>[{esc(', '.join(detection.matched_keywords))}] 새 글 감지</b>",
            "",
            f"📌 <b>{esc(_truncate(post.title, 200))}</b>",
        ]
        if detection.seat_summary:
            lines.append(f"💺 {esc(detection.seat_summary)}")
        if post.body:
            lines.append(f"📝 {esc(_truncate(post.body.replace(chr(10), ' '), 300))}")
        lines += [
            "",
            f'🔗 <a href="{esc(post.url)}">게시글 바로가기</a>',
            f'🎟️ <a href="{esc(config.interpark_booking_url)}">인터파크 예매창 열기</a>',
            "",
            f"<i>{esc(config.gallery_id)} · 글번호 {post.no}"
            + (f" · {esc(post.created_at)}" if post.created_at else "")
            + "</i>",
        ]

        payload = {
            "chat_id": self.chat_id,
            "text": _truncate("\n".join(lines), 4000),
            "parse_mode": "HTML",
            "disable_web_page_preview": False,
        }

        for attempt in range(3):
            try:
                response = requests.post(self.api_url, json=payload, timeout=self.timeout)
                if response.status_code == 200:
                    return True
                logger.error(
                    "Telegram 전송 실패: HTTP %s %s",
                    response.status_code,
                    _truncate(response.text, 200),
                )
            except requests.RequestException as exc:
                logger.error("Telegram 전송 오류: %s", exc)
            time.sleep(2**attempt)
        return False


class ConsoleNotifier:
    """DRY_RUN 모드에서 콘솔로만 출력."""

    name = "console"

    def send(self, detection: Detection, config: Config) -> bool:
        post = detection.post
        logger.info(
            "[DRY-RUN] %s | 키워드=%s | 좌석=%s | %s | 예매=%s",
            post.title,
            ",".join(detection.matched_keywords),
            detection.seat_summary or "-",
            post.url,
            config.interpark_booking_url,
        )
        return True


class MultiNotifier:
    """설정된 모든 채널로 알림을 보낸다. 한 채널이 실패해도 나머지는 계속 시도."""

    name = "multi"

    def __init__(self, notifiers: List[Notifier]) -> None:
        self.notifiers = notifiers

    def send(self, detection: Detection, config: Config) -> bool:
        results = []
        for notifier in self.notifiers:
            try:
                results.append(notifier.send(detection, config))
            except Exception as exc:  # pragma: no cover - 알림 실패로 봇이 죽지 않게
                logger.exception("알림 채널 %s 에서 예외 발생: %s", notifier.name, exc)
                results.append(False)
        return any(results)


def build_notifier(config: Config) -> MultiNotifier:
    notifiers: List[Notifier] = []
    if config.discord_webhook_url:
        notifiers.append(
            DiscordNotifier(config.discord_webhook_url, timeout=config.request_timeout)
        )
    if config.telegram_bot_token and config.telegram_chat_id:
        notifiers.append(
            TelegramNotifier(
                config.telegram_bot_token,
                config.telegram_chat_id,
                timeout=config.request_timeout,
            )
        )
    if config.dry_run or not notifiers:
        notifiers.append(ConsoleNotifier())
    logger.info("활성 알림 채널: %s", ", ".join(n.name for n in notifiers))
    return MultiNotifier(notifiers)
