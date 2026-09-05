import json
import unittest
from unittest import mock

from dcbot.config import Config
from dcbot.models import Detection, Post
from dcbot.notifier import (
    ConsoleNotifier,
    DiscordNotifier,
    MultiNotifier,
    TelegramNotifier,
    build_notifier,
)


def make_detection() -> Detection:
    post = Post(
        no=1005,
        title="VIP 2층 A구역 3열 12번 양도합니다",
        url="https://gall.dcinside.com/mgallery/board/view/?id=vaundy0606&no=1005",
        writer="티켓요정",
        created_at="2024-05-01 12:34:56",
        body="8/15 공연 취소표 풀렸습니다. 165,000원 정가 양도",
    )
    return Detection(
        post=post,
        matched_keywords=["양도", "취소"],
        seat_summary="8/15 · VIP석 · 2층 · A구역 · 3열 · 12번",
    )


class FakeResponse:
    def __init__(self, status_code=204, payload=None):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = json.dumps(self._payload)

    def json(self):
        return self._payload


class DiscordNotifierTest(unittest.TestCase):
    def setUp(self):
        self.config = Config(dry_run=True, interpark_booking_url="https://tickets.interpark.com/goods/24012345")

    def test_payload_contains_links_and_seat_info(self):
        notifier = DiscordNotifier("https://discord.example/webhook")
        with mock.patch("dcbot.notifier.requests.post", return_value=FakeResponse()) as post:
            self.assertTrue(notifier.send(make_detection(), self.config))

        payload = post.call_args.kwargs["json"]
        embed = payload["embeds"][0]
        self.assertEqual(embed["title"], "VIP 2층 A구역 3열 12번 양도합니다")
        self.assertEqual(embed["url"], make_detection().post.url)

        field_values = "\n".join(f["value"] for f in embed["fields"])
        self.assertIn(make_detection().post.url, field_values)
        self.assertIn("https://tickets.interpark.com/goods/24012345", field_values)
        self.assertIn("3열", field_values)

    def test_failure_returns_false(self):
        notifier = DiscordNotifier("https://discord.example/webhook")
        with mock.patch("dcbot.notifier.requests.post", return_value=FakeResponse(500)):
            with mock.patch("dcbot.notifier.time.sleep"):
                self.assertFalse(notifier.send(make_detection(), self.config))


class TelegramNotifierTest(unittest.TestCase):
    def test_message_contains_both_links(self):
        config = Config(dry_run=True, interpark_booking_url="https://tickets.interpark.com/goods/24012345")
        notifier = TelegramNotifier("token", "12345")
        with mock.patch(
            "dcbot.notifier.requests.post", return_value=FakeResponse(200)
        ) as post:
            self.assertTrue(notifier.send(make_detection(), config))

        payload = post.call_args.kwargs["json"]
        self.assertEqual(payload["chat_id"], "12345")
        self.assertEqual(payload["parse_mode"], "HTML")
        self.assertIn("no=1005", payload["text"])
        self.assertIn("tickets.interpark.com/goods/24012345", payload["text"])
        self.assertIn("💺", payload["text"])


class BuildNotifierTest(unittest.TestCase):
    def test_dry_run_uses_console(self):
        config = Config(dry_run=True)
        notifier = build_notifier(config)
        self.assertTrue(any(isinstance(n, ConsoleNotifier) for n in notifier.notifiers))

    def test_both_channels_enabled(self):
        config = Config(
            discord_webhook_url="https://discord.example/webhook",
            telegram_bot_token="token",
            telegram_chat_id="1",
        )
        notifier = build_notifier(config)
        self.assertEqual([n.name for n in notifier.notifiers], ["discord", "telegram"])

    def test_multi_notifier_survives_channel_exception(self):
        class Boom:
            name = "boom"

            def send(self, detection, config):
                raise RuntimeError("네트워크 오류")

        ok = ConsoleNotifier()
        multi = MultiNotifier([Boom(), ok])
        self.assertTrue(multi.send(make_detection(), Config(dry_run=True)))


if __name__ == "__main__":
    unittest.main()
