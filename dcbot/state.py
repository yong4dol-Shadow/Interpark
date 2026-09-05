"""마지막으로 확인한 글 번호 캐싱(JSON 파일)."""

from __future__ import annotations

import json
import logging
import os
import tempfile
from collections import deque
from pathlib import Path
from typing import Deque, Iterable, Optional

logger = logging.getLogger(__name__)


class StateStore:
    """마지막 글 번호 + 최근 알림 이력(중복 알림 방지)을 파일에 보존한다."""

    def __init__(self, path: Path, history_size: int = 500) -> None:
        self.path = Path(path)
        self.history_size = max(10, history_size)
        self.last_no: Optional[int] = None
        self._notified: Deque[int] = deque(maxlen=self.history_size)
        self._notified_set: set[int] = set()
        self.load()

    # ------------------------------------------------------------------
    def load(self) -> None:
        if not self.path.exists():
            logger.info("상태 파일이 없습니다. 첫 실행으로 시작합니다: %s", self.path)
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning("상태 파일을 읽지 못했습니다(%s). 초기화합니다.", exc)
            return

        last_no = data.get("last_no")
        self.last_no = int(last_no) if isinstance(last_no, int) else None
        for no in data.get("notified", [])[-self.history_size :]:
            if isinstance(no, int):
                self._notified.append(no)
        self._notified_set = set(self._notified)
        logger.info(
            "상태 로드 완료: last_no=%s, 알림 이력=%d건", self.last_no, len(self._notified)
        )

    def save(self) -> None:
        payload = {
            "last_no": self.last_no,
            "notified": list(self._notified),
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # 중간에 프로세스가 죽어도 파일이 깨지지 않도록 원자적으로 교체한다.
        fd, tmp_path = tempfile.mkstemp(dir=str(self.path.parent), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fp:
                json.dump(payload, fp, ensure_ascii=False, indent=2)
            os.replace(tmp_path, self.path)
        except OSError as exc:  # pragma: no cover - 디스크 오류
            logger.error("상태 저장 실패: %s", exc)
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)

    # ------------------------------------------------------------------
    @property
    def is_first_run(self) -> bool:
        return self.last_no is None

    def is_new(self, post_no: int) -> bool:
        """아직 처리하지 않은 글인지."""
        if post_no in self._notified_set:
            return False
        return self.last_no is None or post_no > self.last_no

    def mark_notified(self, post_no: int) -> None:
        if post_no in self._notified_set:
            return
        if len(self._notified) == self._notified.maxlen:
            self._notified_set.discard(self._notified[0])
        self._notified.append(post_no)
        self._notified_set.add(post_no)

    def update_last_no(self, post_numbers: Iterable[int]) -> None:
        numbers = [n for n in post_numbers if isinstance(n, int)]
        if not numbers:
            return
        highest = max(numbers)
        if self.last_no is None or highest > self.last_no:
            self.last_no = highest
