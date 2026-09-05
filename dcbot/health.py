"""Cloud Run 등 '포트를 열어야 하는' 환경을 위한 초경량 헬스체크 서버.

PORT 환경 변수가 있을 때만 데몬 스레드로 기동한다. 로컬/도커 실행에는 영향이 없다.
"""

from __future__ import annotations

import json
import logging
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Callable, Optional

logger = logging.getLogger(__name__)


def _make_handler(status_provider: Callable[[], dict]):
    class HealthHandler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_GET(self):  # noqa: N802 (http.server 규약)
            body = json.dumps(status_provider(), ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):  # 접근 로그 억제
            pass

    return HealthHandler


def start_health_server(
    status_provider: Callable[[], dict], port: Optional[int] = None
) -> Optional[ThreadingHTTPServer]:
    """PORT 가 지정된 경우에만 헬스체크 서버를 띄우고 서버 객체를 반환한다."""
    if port is None:
        raw_port = os.getenv("PORT")
        if not raw_port:
            return None
        try:
            port = int(raw_port)
        except ValueError:
            logger.warning("PORT 값이 올바르지 않습니다: %s", raw_port)
            return None

    server = ThreadingHTTPServer(("0.0.0.0", port), _make_handler(status_provider))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    logger.info("헬스체크 서버 기동: http://0.0.0.0:%d/", port)
    return server
