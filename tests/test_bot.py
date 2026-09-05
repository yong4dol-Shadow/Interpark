import tempfile
import unittest
from pathlib import Path
from typing import Dict, List

from dcbot.bot import MonitorBot
from dcbot.config import Config
from dcbot.models import Post
from dcbot.state import StateStore


class FakeScraper:
    """네트워크 없이 동작하는 스크레이퍼 대역."""

    class _Client:
        def rotate_user_agent(self, mobile: bool = False):
            pass

    def __init__(self, posts: List[Post], bodies: Dict[int, str] | None = None):
        self.posts = posts
        self.bodies = bodies or {}
        self.body_calls: List[int] = []
        self.client = self._Client()

    def fetch_list(self, page: int = 1) -> List[Post]:
        return list(self.posts) if page == 1 else []

    def fetch_body(self, post: Post) -> str:
        self.body_calls.append(post.no)
        return self.bodies.get(post.no, "")

    def close(self):
        pass


class FakeNotifier:
    name = "fake"

    def __init__(self, ok: bool = True):
        self.ok = ok
        self.sent = []

    def send(self, detection, config) -> bool:
        if self.ok:
            self.sent.append(detection)
        return self.ok


def make_post(no: int, title: str) -> Post:
    return Post(no=no, title=title, url=f"https://gall.dcinside.com/x?no={no}")


class MonitorBotTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.state_path = Path(self.tmp.name) / "last_seen.json"
        self.config = Config(
            dry_run=True,
            state_file=self.state_path,
            fetch_body=False,
            body_fetch_delay_min=0.0,
            body_fetch_delay_max=0.0,
        )

    def tearDown(self):
        self.tmp.cleanup()

    def _bot(self, scraper, notifier=None) -> MonitorBot:
        return MonitorBot(
            self.config,
            scraper=scraper,
            notifier=notifier or FakeNotifier(),
            state=StateStore(self.state_path, self.config.seen_history_size),
        )

    def test_first_run_only_sets_baseline(self):
        scraper = FakeScraper([make_post(10, "취소표 양도합니다")])
        notifier = FakeNotifier()
        bot = self._bot(scraper, notifier)

        self.assertEqual(bot.run_once(), [])
        self.assertEqual(notifier.sent, [])
        self.assertEqual(bot.state.last_no, 10)

    def test_detects_new_post_with_keyword(self):
        scraper = FakeScraper([make_post(10, "잡담")])
        notifier = FakeNotifier()
        bot = self._bot(scraper, notifier)
        bot.run_once()  # 기준점 설정

        scraper.posts = [make_post(11, "8/15 취켓팅 성공 A구역 3열 12번"), make_post(10, "잡담")]
        detections = bot.run_once()

        self.assertEqual(len(detections), 1)
        self.assertEqual(detections[0].post.no, 11)
        self.assertIn("취켓팅", detections[0].matched_keywords)
        self.assertIn("3열", detections[0].seat_summary)
        self.assertEqual(len(notifier.sent), 1)

    def test_no_duplicate_notification(self):
        scraper = FakeScraper([make_post(10, "잡담")])
        notifier = FakeNotifier()
        bot = self._bot(scraper, notifier)
        bot.run_once()

        scraper.posts = [make_post(11, "양도합니다")]
        bot.run_once()
        bot.run_once()
        bot.run_once()

        self.assertEqual(len(notifier.sent), 1)

    def test_ignores_posts_without_keyword(self):
        scraper = FakeScraper([make_post(10, "잡담")])
        notifier = FakeNotifier()
        bot = self._bot(scraper, notifier)
        bot.run_once()

        scraper.posts = [make_post(11, "오늘 공연 후기")]
        self.assertEqual(bot.run_once(), [])
        self.assertEqual(notifier.sent, [])
        self.assertEqual(bot.state.last_no, 11)

    def test_body_keyword_detection(self):
        self.config.fetch_body = True
        scraper = FakeScraper(
            [make_post(10, "잡담")],
            bodies={11: "제목에는 없지만 본문에 취소표 풀림 정보가 있어요. B구역 2열 5번"},
        )
        notifier = FakeNotifier()
        bot = self._bot(scraper, notifier)
        bot.run_once()

        scraper.posts = [make_post(11, "이거 보세요")]
        detections = bot.run_once()

        self.assertEqual(len(detections), 1)
        self.assertTrue(detections[0].matched_in_body)
        self.assertIn("2열", detections[0].seat_summary)
        self.assertEqual(scraper.body_calls, [11])

    def test_failed_notification_is_retried_next_cycle(self):
        scraper = FakeScraper([make_post(10, "잡담")])
        failing = FakeNotifier(ok=False)
        bot = self._bot(scraper, failing)
        bot.run_once()

        scraper.posts = [make_post(11, "양도합니다")]
        self.assertEqual(bot.run_once(), [])
        # 알림 실패 → last_no 가 전진하지 않아 다음 사이클에 다시 시도한다.
        self.assertEqual(bot.state.last_no, 10)

        bot.notifier = FakeNotifier()
        detections = bot.run_once()
        self.assertEqual(len(detections), 1)
        self.assertEqual(bot.state.last_no, 11)

    def test_body_budget_defers_remaining_posts(self):
        self.config.fetch_body = True
        self.config.max_body_fetch_per_cycle = 1
        scraper = FakeScraper([make_post(10, "잡담")])
        notifier = FakeNotifier()
        bot = self._bot(scraper, notifier)
        bot.run_once()

        scraper.posts = [make_post(11, "양도합니다"), make_post(12, "취소표")]
        bot.run_once()
        self.assertEqual(bot.state.last_no, 11)
        self.assertEqual(len(notifier.sent), 1)

        bot.run_once()
        self.assertEqual(bot.state.last_no, 12)
        self.assertEqual(len(notifier.sent), 2)

    def test_empty_list_is_safe(self):
        bot = self._bot(FakeScraper([]))
        self.assertEqual(bot.run_once(), [])


if __name__ == "__main__":
    unittest.main()
