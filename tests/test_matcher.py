import unittest

from dcbot.matcher import KeywordMatcher


class MatcherTest(unittest.TestCase):
    def setUp(self):
        self.matcher = KeywordMatcher(["취소", "취켓팅", "양도", "풀림"])

    def test_single_match(self):
        self.assertEqual(self.matcher.match("취소표 나왔어요"), ["취소"])

    def test_multiple_matches(self):
        hits = self.matcher.match("취소표 양도합니다")
        self.assertIn("취소", hits)
        self.assertIn("양도", hits)

    def test_spacing_evasion(self):
        self.assertEqual(self.matcher.match("취 켓 팅 성공"), ["취켓팅"])

    def test_no_match(self):
        self.assertEqual(self.matcher.match("오늘 공연 좋았다"), [])

    def test_exclude_keyword(self):
        matcher = KeywordMatcher(["양도"], ["구합니다"])
        self.assertEqual(matcher.match("양도 구합니다"), [])
        self.assertEqual(matcher.match("양도합니다"), ["양도"])


if __name__ == "__main__":
    unittest.main()
