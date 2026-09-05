import unittest
from pathlib import Path

from dcbot.config import Config
from dcbot.scraper import DcinsideScraper

FIXTURES = Path(__file__).parent / "fixtures"


def read(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


class ScraperParseTest(unittest.TestCase):
    def setUp(self):
        self.config = Config(dry_run=True)
        # 네트워크를 쓰지 않는 파싱 테스트이므로 클라이언트는 None 대체 객체로 둔다.
        self.scraper = DcinsideScraper.__new__(DcinsideScraper)
        self.scraper.config = self.config

    def test_parse_list_skips_notice_and_ad(self):
        posts = self.scraper.parse_list(read("list_sample.html"))
        self.assertEqual([p.no for p in posts], [1005, 1004])

    def test_parse_list_fields(self):
        posts = self.scraper.parse_list(read("list_sample.html"))
        post = posts[0]
        self.assertEqual(post.title, "VIP 2층 A구역 3열 12번 양도합니다")
        self.assertEqual(post.writer, "티켓요정")
        self.assertEqual(post.created_at, "2024-05-01 12:34:56")
        self.assertEqual(post.reply_count, 7)
        self.assertEqual(post.view_count, 1234)
        self.assertTrue(post.url.startswith("https://gall.dcinside.com/mgallery/board/view/"))
        self.assertIn("no=1005", post.url)

    def test_parse_list_mobile(self):
        posts = self.scraper.parse_list_mobile(read("list_mobile_sample.html"))
        self.assertEqual(sorted(p.no for p in posts), [1004, 1005])
        self.assertEqual(posts[0].title, "VIP 2층 A구역 3열 12번 양도합니다")

    def test_parse_body_strips_scripts(self):
        body = DcinsideScraper.parse_body(read("view_sample.html"))
        self.assertIn("취소표", body)
        self.assertIn("A구역 3열 12번", body)
        self.assertNotIn("var a = 1", body)
        self.assertNotIn("color:red", body)

    def test_parse_body_missing_node(self):
        self.assertEqual(DcinsideScraper.parse_body("<html><body>없음</body></html>"), "")

    def test_parse_list_empty_html(self):
        self.assertEqual(self.scraper.parse_list("<html></html>"), [])


if __name__ == "__main__":
    unittest.main()
