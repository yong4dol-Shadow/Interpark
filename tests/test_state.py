import tempfile
import unittest
from pathlib import Path

from dcbot.state import StateStore


class StateStoreTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "state" / "last_seen.json"

    def tearDown(self):
        self.tmp.cleanup()

    def test_first_run(self):
        store = StateStore(self.path)
        self.assertTrue(store.is_first_run)
        self.assertTrue(store.is_new(100))

    def test_persist_roundtrip(self):
        store = StateStore(self.path)
        store.update_last_no([10, 30, 20])
        store.mark_notified(30)
        store.save()

        reloaded = StateStore(self.path)
        self.assertEqual(reloaded.last_no, 30)
        self.assertFalse(reloaded.is_first_run)
        self.assertFalse(reloaded.is_new(30))
        self.assertFalse(reloaded.is_new(29))
        self.assertTrue(reloaded.is_new(31))

    def test_notified_prevents_duplicate_even_if_greater(self):
        store = StateStore(self.path)
        store.update_last_no([10])
        store.mark_notified(15)
        self.assertFalse(store.is_new(15))

    def test_history_is_bounded(self):
        store = StateStore(self.path, history_size=10)
        for no in range(100):
            store.mark_notified(no)
        store.save()
        reloaded = StateStore(self.path, history_size=10)
        self.assertFalse(reloaded.is_new(99))
        # 오래된 번호는 이력에서 밀려나지만 last_no 로 걸러진다.
        self.assertEqual(len(reloaded._notified), 10)

    def test_corrupted_file_is_tolerated(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text("{ not json", encoding="utf-8")
        store = StateStore(self.path)
        self.assertTrue(store.is_first_run)


if __name__ == "__main__":
    unittest.main()
