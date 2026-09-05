"""디시인사이드 갤러리 리스트/본문 파서."""

from __future__ import annotations

import logging
import re
from typing import List, Optional
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from .config import Config
from .http_client import BlockedError, HttpClient
from .models import Post

logger = logging.getLogger(__name__)

_NUM_RE = re.compile(r"\d+")
_MOBILE_NO_RE = re.compile(r"/board/[^/]+/(\d+)")


def _to_int(text: Optional[str], default: int = 0) -> int:
    if not text:
        return default
    match = _NUM_RE.search(text.replace(",", ""))
    return int(match.group()) if match else default


def _soup(html: str) -> BeautifulSoup:
    try:
        return BeautifulSoup(html, "lxml")
    except Exception:  # pragma: no cover - lxml 미설치 환경 대비
        return BeautifulSoup(html, "html.parser")


class DcinsideScraper:
    """PC 웹을 기본으로 하고, 실패 시 모바일 웹으로 폴백한다."""

    def __init__(self, config: Config, client: Optional[HttpClient] = None) -> None:
        self.config = config
        self.client = client or HttpClient(
            timeout=config.request_timeout,
            max_backoff=config.max_backoff_seconds,
        )

    # ------------------------------------------------------------------
    # 리스트
    # ------------------------------------------------------------------
    def fetch_list(self, page: int = 1) -> List[Post]:
        """갤러리 리스트 한 페이지를 읽어 글 목록을 돌려준다."""
        try:
            response = self.client.get(
                self.config.list_url,
                params={"id": self.config.gallery_id, "page": page},
                referer="https://gall.dcinside.com/",
            )
            posts = self.parse_list(response.text)
            if posts:
                return posts
            logger.warning("PC 리스트에서 글을 찾지 못했습니다. 모바일로 폴백합니다.")
        except BlockedError as exc:
            logger.warning("PC 리스트 요청 실패(%s). 모바일로 폴백합니다.", exc)

        return self._fetch_list_mobile(page)

    def _fetch_list_mobile(self, page: int = 1) -> List[Post]:
        response = self.client.get(
            self.config.mobile_list_url,
            params={"page": page},
            referer="https://m.dcinside.com/",
            mobile=True,
        )
        return self.parse_list_mobile(response.text)

    # ------------------------------------------------------------------
    def parse_list(self, html: str) -> List[Post]:
        """PC 리스트 HTML 파싱. 공지/광고 행은 제외한다."""
        soup = _soup(html)
        posts: List[Post] = []

        for row in soup.select("tr.ub-content"):
            num_cell = row.select_one("td.gall_num")
            raw_no = (num_cell.get_text(strip=True) if num_cell else "") or str(
                row.get("data-no") or ""
            )
            if not raw_no.isdigit():
                # 공지, 설문, AD 등
                continue

            link = row.select_one("td.gall_tit a[href]")
            if not link:
                continue

            title = link.get_text(" ", strip=True)
            if not title:
                continue

            writer_cell = row.select_one("td.gall_writer")
            writer = ""
            if writer_cell:
                writer = str(writer_cell.get("data-nick") or "") or writer_cell.get_text(
                    " ", strip=True
                )

            date_cell = row.select_one("td.gall_date")
            created_at = ""
            if date_cell:
                created_at = str(date_cell.get("title") or "") or date_cell.get_text(
                    strip=True
                )

            reply_el = row.select_one("td.gall_tit .reply_num")
            posts.append(
                Post(
                    no=int(raw_no),
                    title=title,
                    url=urljoin("https://gall.dcinside.com/", str(link.get("href"))),
                    writer=writer,
                    created_at=created_at,
                    reply_count=_to_int(reply_el.get_text(strip=True) if reply_el else ""),
                    view_count=_to_int(
                        row.select_one("td.gall_count").get_text(strip=True)
                        if row.select_one("td.gall_count")
                        else ""
                    ),
                )
            )

        return posts

    def parse_list_mobile(self, html: str) -> List[Post]:
        """모바일 리스트 HTML 파싱."""
        soup = _soup(html)
        posts: List[Post] = []

        for item in soup.select("ul.gall-detail-lst li, ul.gall-lst li"):
            link = item.select_one("a[href*='/board/']")
            if not link:
                continue
            href = str(link.get("href") or "")
            match = _MOBILE_NO_RE.search(href)
            if not match:
                continue

            subject = item.select_one(".subjectin, .subject-add, .txt")
            title = (subject or link).get_text(" ", strip=True)
            if not title:
                continue

            writer_el = item.select_one(".ginfo li:nth-of-type(1), .nick")
            date_el = item.select_one(".ginfo li:last-child, .date")
            posts.append(
                Post(
                    no=int(match.group(1)),
                    title=title,
                    url=self.config.post_url(int(match.group(1))),
                    writer=writer_el.get_text(strip=True) if writer_el else "",
                    created_at=date_el.get_text(strip=True) if date_el else "",
                )
            )

        # 중복 제거(모바일은 같은 글이 여러 블록에 나올 수 있음)
        unique: dict[int, Post] = {}
        for post in posts:
            unique.setdefault(post.no, post)
        return list(unique.values())

    # ------------------------------------------------------------------
    # 본문
    # ------------------------------------------------------------------
    def fetch_body(self, post: Post) -> str:
        """게시글 본문 텍스트를 가져온다. 실패하면 빈 문자열."""
        try:
            response = self.client.get(
                post.url,
                referer=self.config.gallery_url,
            )
            return self.parse_body(response.text)
        except BlockedError as exc:
            logger.warning("본문 조회 실패(no=%s): %s", post.no, exc)
            return ""

    @staticmethod
    def parse_body(html: str) -> str:
        soup = _soup(html)
        node = soup.select_one(
            "div.write_div, div.writing_view_box, div.thum-txtin, #dgn_contents_wrap"
        )
        if node is None:
            return ""
        for tag in node.select("script, style, iframe"):
            tag.decompose()
        return node.get_text("\n", strip=True)

    def close(self) -> None:
        self.client.close()
