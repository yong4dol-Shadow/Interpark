import unittest

from dcbot.seatinfo import extract_seat_info, summarize_seat_info


class SeatInfoTest(unittest.TestCase):
    def test_full_seat_line(self):
        text = "8월 15일 VIP석 2층 A구역 3열 12번 2연석 165,000원 양도"
        info = extract_seat_info(text)
        self.assertEqual(info["date"], ["8/15"])
        self.assertEqual(info["grade"], ["VIP석"])
        self.assertEqual(info["floor"], ["2층"])
        self.assertEqual(info["zone"], ["A구역"])
        self.assertEqual(info["row"], ["3열"])
        self.assertIn("12번", info["seat"])
        self.assertEqual(info["count"], ["2매"])
        self.assertEqual(info["price"], ["165,000원"])

    def test_summary_contains_core_fields(self):
        summary = summarize_seat_info("R석 5열 7번 1매 취소표 풀림 8/15")
        self.assertIn("5열", summary)
        self.assertIn("7번", summary)
        self.assertIn("R석", summary)

    def test_no_seat_info_returns_empty(self):
        self.assertEqual(summarize_seat_info("오늘 날씨가 좋네요"), "")
        # 가격만 있고 좌석 정보가 없으면 요약하지 않는다.
        self.assertEqual(summarize_seat_info("굿즈 30,000원에 팝니다"), "")

    def test_spaced_notation(self):
        summary = summarize_seat_info("1 층 스탠딩 200 번대 풀림")
        self.assertIn("1층", summary)
        self.assertIn("스탠딩", summary)

    def test_empty_input(self):
        self.assertEqual(summarize_seat_info(""), "")
        self.assertEqual(extract_seat_info(""), {})


if __name__ == "__main__":
    unittest.main()
