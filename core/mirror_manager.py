"""Mirror discovery and health checks for scholar mirrors."""

from __future__ import annotations

import logging
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional
from urllib.parse import quote, urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

load_dotenv(Path(__file__).resolve().parent.parent / "config" / ".env")


DEFAULT_MIRROR_URLS = [
    "https://scholar.lanfanshu.cn",
    "https://xueshu.lanfanshu.cn",
    "https://sc.panda985.com",
    "https://xs.cljtscd.com",
    "https://so.cljtscd.com",
    "https://so1.cljtscd.com",
    "https://so2.cljtscd.com",
    "https://so3.cljtscd.com",
    "https://scholar.google.com.hk",
]

DEFAULT_NAV_SOURCE_URLS = [
    "https://ac.scmor.com/",
]

SCMOR_FALLBACK_MIRRORS = [
    "https://scholar.lanfanshu.cn",
    "https://xueshu.lanfanshu.cn",
    "https://sc.panda985.com",
    "https://xs.cljtscd.com",
    "https://so.cljtscd.com",
    "https://so1.cljtscd.com",
    "https://so2.cljtscd.com",
    "https://so3.cljtscd.com",
]

NAV_HOST_BLACKLIST = {
    "ac.scmor.com",
    "www.scmor.com",
    "scmor.com",
}

MIRROR_HOST_HINTS = (
    "scholar",
    "xueshu",
    "lanfanshu",
    "panda985",
    "cljtscd",
    "google.com.hk",
)

MIRROR_TEXT_HINTS = (
    "scholar",
    "google scholar",
    "谷歌学术",
    "学术镜像",
    "学术搜索",
)


def _split_env_list(value: str) -> list[str]:
    items = re.split(r"[;,\n\r]+", value)
    return [item.strip() for item in items if item.strip()]


def get_env_nav_sources() -> list[str]:
    value = os.getenv("CHEMDEEP_LANFANSHU_MIRROR_NAV_URLS", "")
    return [url for url in _split_env_list(value) if url.startswith("http")]


def get_env_direct_mirrors() -> list[str]:
    value = os.getenv("CHEMDEEP_LANFANSHU_MIRROR_URLS", "")
    return [url for url in _split_env_list(value) if url.startswith("http")]


@dataclass
class MirrorInfo:
    url: str
    name: str
    is_working: bool = True
    last_checked: float = 0.0
    response_time: float = 0.0
    consecutive_failures: int = 0
    scholar_path: str = "/scholar"


@dataclass
class HealthCheckResult:
    mirror: MirrorInfo
    is_healthy: bool
    response_time: float
    has_results: bool
    error: Optional[str] = None


def _mirror_info_from_url(
    url: str, source_name: str = "mirror"
) -> Optional[MirrorInfo]:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None

    base_url = f"{parsed.scheme}://{parsed.netloc}"
    scholar_path = parsed.path if parsed.path and parsed.path != "/" else "/scholar"
    if "scholar" not in scholar_path.lower():
        scholar_path = "/scholar"

    return MirrorInfo(
        url=base_url,
        name=f"{source_name}: {parsed.netloc}",
        scholar_path=scholar_path,
    )


def _is_probable_mirror(candidate_url: str, link_text: str = "") -> bool:
    parsed = urlparse(candidate_url)
    host = parsed.netloc.lower()
    path = parsed.path.lower()
    text = link_text.lower()

    if host in NAV_HOST_BLACKLIST:
        return False

    if any(hint in host for hint in MIRROR_HOST_HINTS):
        return True

    if "scholar" in path or "xueshu" in path:
        return True

    return any(hint in text for hint in MIRROR_TEXT_HINTS)


def _extract_candidates_from_html(nav_url: str, html: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    candidates: list[str] = []

    for tag in soup.select("a[href]"):
        href_value = tag.get("href")
        if not isinstance(href_value, str):
            continue
        href = href_value.strip()
        if not href:
            continue
        absolute_url = urljoin(nav_url, href)
        text = tag.get_text(" ", strip=True)
        if _is_probable_mirror(absolute_url, text):
            candidates.append(absolute_url)

    raw_urls = re.findall(r"https?://[^\s'\"<>]+", html)
    for raw_url in raw_urls:
        if _is_probable_mirror(raw_url):
            candidates.append(raw_url)

    if "ac.scmor.com" in nav_url:
        candidates.extend(SCMOR_FALLBACK_MIRRORS)

    deduped: list[str] = []
    seen: set[str] = set()
    for url in candidates:
        info = _mirror_info_from_url(url)
        if not info:
            continue
        key = f"{info.url}{info.scholar_path}"
        if key in seen:
            continue
        seen.add(key)
        deduped.append(url)
    return deduped


class MirrorManager:
    def __init__(
        self,
        mirrors: Optional[list[MirrorInfo]] = None,
        nav_sources: Optional[list[str]] = None,
        nav_fetch_interval: int = 6 * 60 * 60,
        max_consecutive_failures: int = 3,
        health_check_timeout: int = 10,
    ):
        self.nav_sources = (
            nav_sources or get_env_nav_sources() or list(DEFAULT_NAV_SOURCE_URLS)
        )
        configured_mirrors = get_env_direct_mirrors()
        seed_mirrors = mirrors or [
            _mirror_info_from_url(url, "default") for url in DEFAULT_MIRROR_URLS
        ]
        if configured_mirrors:
            seed_mirrors = [
                _mirror_info_from_url(url, "env") for url in configured_mirrors
            ] + list(seed_mirrors)

        self.mirrors = [mirror for mirror in seed_mirrors if mirror is not None]
        self.last_nav_fetch = 0.0
        self.nav_fetch_interval = nav_fetch_interval
        self.max_consecutive_failures = max_consecutive_failures
        self.health_check_timeout = health_check_timeout

    def refresh_from_navigation_sources(self, force: bool = False) -> None:
        now = time.time()
        if (
            not force
            and self.last_nav_fetch
            and now - self.last_nav_fetch < self.nav_fetch_interval
        ):
            return

        for nav_url in self.nav_sources:
            try:
                response = requests.get(
                    nav_url,
                    timeout=self.health_check_timeout,
                    headers={
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                    },
                )
                response.raise_for_status()
                discovered = _extract_candidates_from_html(nav_url, response.text)
                self._merge_urls(
                    discovered, source_name=f"nav:{urlparse(nav_url).netloc}"
                )
            except Exception as exc:
                logger.debug("mirror navigation fetch failed for %s: %s", nav_url, exc)

        self.last_nav_fetch = now

    def _merge_urls(self, urls: Iterable[str], source_name: str) -> None:
        existing = {f"{m.url}{m.scholar_path}" for m in self.mirrors}
        for url in urls:
            info = _mirror_info_from_url(url, source_name)
            if not info:
                continue
            key = f"{info.url}{info.scholar_path}"
            if key in existing:
                continue
            existing.add(key)
            self.mirrors.append(info)

    def get_best_mirror(self) -> Optional[MirrorInfo]:
        working = self.get_working_mirrors()
        return working[0] if working else None

    def get_working_mirrors(self) -> list[MirrorInfo]:
        self.refresh_from_navigation_sources()
        mirrors = [mirror for mirror in self.mirrors if mirror.is_working]
        return sorted(mirrors, key=lambda mirror: mirror.response_time)

    def get_all_mirrors(self) -> list[MirrorInfo]:
        self.refresh_from_navigation_sources()
        return list(self.mirrors)

    def check_mirror_health(self, mirror: MirrorInfo) -> HealthCheckResult:
        start_time = time.time()
        test_query = "machine learning"
        test_url = f"{mirror.url}{mirror.scholar_path}?q={quote(test_query)}&hl=zh-CN&as_sdt=0,5"

        try:
            response = requests.get(
                test_url,
                timeout=self.health_check_timeout,
                allow_redirects=True,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                },
            )
            response_time = time.time() - start_time
            soup = BeautifulSoup(response.text, "html.parser")
            has_results = bool(soup.select(".gs_r.gs_or.gs_scl"))
            is_healthy = response.status_code == 200 and has_results
            error = (
                None
                if is_healthy
                else f"Status: {response.status_code}, Results: {int(has_results)}"
            )
            return HealthCheckResult(
                mirror, is_healthy, response_time, has_results, error
            )
        except Exception as exc:
            response_time = time.time() - start_time
            return HealthCheckResult(mirror, False, response_time, False, str(exc))

    def check_all_mirrors(self) -> list[HealthCheckResult]:
        self.refresh_from_navigation_sources(force=True)
        results: list[HealthCheckResult] = []
        for mirror in self.mirrors:
            result = self.check_mirror_health(mirror)
            mirror.last_checked = time.time()
            mirror.response_time = result.response_time
            if result.is_healthy:
                mirror.is_working = True
                mirror.consecutive_failures = 0
            else:
                mirror.consecutive_failures += 1
                mirror.is_working = (
                    mirror.consecutive_failures < self.max_consecutive_failures
                )
            results.append(result)
        return results

    def mark_mirror_failed(self, mirror_url: str) -> None:
        for mirror in self.mirrors:
            if mirror.url != mirror_url:
                continue
            mirror.consecutive_failures += 1
            mirror.last_checked = time.time()
            mirror.is_working = (
                mirror.consecutive_failures < self.max_consecutive_failures
            )
            return

    def mark_mirror_success(self, mirror_url: str, response_time: float) -> None:
        for mirror in self.mirrors:
            if mirror.url != mirror_url:
                continue
            mirror.is_working = True
            mirror.consecutive_failures = 0
            mirror.response_time = response_time
            mirror.last_checked = time.time()
            return

    def get_status_summary(self) -> str:
        working = [mirror for mirror in self.mirrors if mirror.is_working]
        failed = [mirror for mirror in self.mirrors if not mirror.is_working]
        lines = [
            f"Mirror Status: {len(working)} working, {len(failed)} failed",
            "Working mirrors (sorted by response time):",
        ]
        for mirror in sorted(working, key=lambda item: item.response_time):
            lines.append(f"  - {mirror.name}: {mirror.response_time:.2f}s")
        if failed:
            lines.append("Failed mirrors:")
            for mirror in failed:
                lines.append(
                    f"  - {mirror.name}: {mirror.consecutive_failures} failures"
                )
        return "\n".join(lines)
