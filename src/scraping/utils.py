"""Scraping utilities: rate limiting, caching, retries, and async HTTP client."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import random
import time
from dataclasses import dataclass, field
from pathlib import Path

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4_1) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4.1 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 Edg/124.0.0.0",
]

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CACHE_DIR = PROJECT_ROOT / "data" / "raw" / "cache"


@dataclass
class ScraperConfig:
    """Configurable settings for the scraper."""

    requests_per_minute: int = 20
    max_retries: int = 3
    retry_base_delay: float = 2.0
    cache_dir: Path = field(default_factory=lambda: DEFAULT_CACHE_DIR)
    cache_ttl_seconds: int = 86400  # 24 hours
    timeout: float = 30.0
    user_agents: list[str] = field(default_factory=lambda: list(USER_AGENTS))


# ---------------------------------------------------------------------------
# Rate Limiter
# ---------------------------------------------------------------------------


class RateLimiter:
    """Token-bucket style rate limiter enforcing max N requests per minute."""

    def __init__(self, requests_per_minute: int = 20) -> None:
        self._rpm = requests_per_minute
        self._min_interval = 60.0 / requests_per_minute
        self._timestamps: list[float] = []
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        """Wait until a request slot is available."""
        async with self._lock:
            now = time.monotonic()
            # Purge timestamps older than 60 seconds
            cutoff = now - 60.0
            self._timestamps = [t for t in self._timestamps if t > cutoff]

            if len(self._timestamps) >= self._rpm:
                wait = self._timestamps[0] - cutoff
                if wait > 0:
                    logger.debug("Rate limiter: sleeping %.2fs", wait)
                    await asyncio.sleep(wait)

            self._timestamps.append(time.monotonic())


# ---------------------------------------------------------------------------
# Disk Cache
# ---------------------------------------------------------------------------


class DiskCache:
    """Disk-based HTML cache keyed by URL hash with configurable TTL."""

    def __init__(self, cache_dir: Path, ttl_seconds: int) -> None:
        self._cache_dir = cache_dir
        self._ttl = ttl_seconds
        self._cache_dir.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _url_hash(url: str) -> str:
        return hashlib.sha256(url.encode()).hexdigest()

    def _meta_path(self, url_hash: str) -> Path:
        return self._cache_dir / f"{url_hash}.meta.json"

    def _html_path(self, url_hash: str) -> Path:
        return self._cache_dir / f"{url_hash}.html"

    def get(self, url: str) -> str | None:
        """Return cached HTML if present and not expired, else None."""
        h = self._url_hash(url)
        meta_path = self._meta_path(h)
        html_path = self._html_path(h)

        if not meta_path.exists() or not html_path.exists():
            return None

        try:
            meta = json.loads(meta_path.read_text())
            cached_at = meta.get("cached_at", 0)
            if time.time() - cached_at > self._ttl:
                logger.debug("Cache expired for %s", url)
                return None
            logger.debug("Cache hit for %s", url)
            return html_path.read_text(encoding="utf-8")
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Cache read error for %s: %s", url, exc)
            return None

    def put(self, url: str, html: str) -> None:
        """Store HTML and metadata to disk."""
        h = self._url_hash(url)
        self._html_path(h).write_text(html, encoding="utf-8")
        self._meta_path(h).write_text(
            json.dumps({"url": url, "cached_at": time.time()}),
            encoding="utf-8",
        )
        logger.debug("Cached %s (%d bytes)", url, len(html))

    def invalidate(self, url: str) -> None:
        """Remove a cached entry."""
        h = self._url_hash(url)
        for p in (self._html_path(h), self._meta_path(h)):
            p.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Async HTTP Client
# ---------------------------------------------------------------------------


class ScraperClient:
    """Async HTTP client integrating rate limiting, caching, and retries."""

    def __init__(self, config: ScraperConfig | None = None) -> None:
        self.config = config or ScraperConfig()
        self._rate_limiter = RateLimiter(self.config.requests_per_minute)
        self._cache = DiskCache(self.config.cache_dir, self.config.cache_ttl_seconds)
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> ScraperClient:
        self._client = httpx.AsyncClient(
            timeout=self.config.timeout,
            follow_redirects=True,
        )
        return self

    async def __aexit__(self, *exc: object) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    def _random_headers(self) -> dict[str, str]:
        return {
            "User-Agent": random.choice(self.config.user_agents),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }

    async def fetch(self, url: str, *, bypass_cache: bool = False) -> str:
        """Fetch a URL with caching, rate limiting, and retries.

        Returns the response HTML as a string.

        Raises:
            httpx.HTTPStatusError: after all retries are exhausted.
        """
        if not bypass_cache:
            cached = self._cache.get(url)
            if cached is not None:
                return cached

        if self._client is None:
            raise RuntimeError("ScraperClient must be used as an async context manager")

        last_exc: Exception | None = None
        for attempt in range(1, self.config.max_retries + 1):
            await self._rate_limiter.acquire()
            try:
                resp = await self._client.get(url, headers=self._random_headers())
                resp.raise_for_status()
                html = resp.text
                self._cache.put(url, html)
                return html
            except (httpx.HTTPStatusError, httpx.TransportError) as exc:
                last_exc = exc
                if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code == 429:
                    delay = self.config.retry_base_delay * (2**attempt)
                    logger.warning("429 Too Many Requests for %s, retrying in %.1fs", url, delay)
                elif isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code < 500:
                    # Client errors (other than 429) are not retryable
                    logger.error("HTTP %d for %s — not retrying", exc.response.status_code, url)
                    raise
                else:
                    delay = self.config.retry_base_delay * (2 ** (attempt - 1))
                    logger.warning(
                        "Attempt %d/%d failed for %s: %s — retrying in %.1fs",
                        attempt,
                        self.config.max_retries,
                        url,
                        exc,
                        delay,
                    )
                await asyncio.sleep(delay)

        logger.error("All %d retries exhausted for %s", self.config.max_retries, url)
        raise last_exc  # type: ignore[misc]

    async def fetch_soup(self, url: str, *, bypass_cache: bool = False) -> BeautifulSoup:
        """Fetch a URL and return a parsed BeautifulSoup object."""
        html = await self.fetch(url, bypass_cache=bypass_cache)
        return parse_html(html)


# ---------------------------------------------------------------------------
# HTML Parsing Helper
# ---------------------------------------------------------------------------


def parse_html(html: str, *, parser: str = "lxml") -> BeautifulSoup:
    """Parse an HTML string with BeautifulSoup.

    Args:
        html: Raw HTML string.
        parser: Parser backend — ``"lxml"`` (fast, default) or ``"html.parser"``.

    Returns:
        A BeautifulSoup document tree.
    """
    return BeautifulSoup(html, parser)


# ---------------------------------------------------------------------------
# Synchronous Cached Scraper (for modules that use synchronous scraping)
# ---------------------------------------------------------------------------


class CachedScraper:
    """Synchronous scraper with disk caching and rate limiting.

    Used by scrapers that don't need async (e.g., sports_ref.py).
    """

    def __init__(
        self,
        rate_limit: float = 3.0,
        cache_dir: Path | None = None,
        cache_ttl: int = 86400,
    ) -> None:
        self._rate_limit = rate_limit  # seconds between requests
        self._cache = DiskCache(
            cache_dir or DEFAULT_CACHE_DIR,
            cache_ttl,
        )
        self._last_request: float = 0.0
        self._client = httpx.Client(
            timeout=30.0,
            follow_redirects=True,
        )

    def _wait_for_rate_limit(self) -> None:
        elapsed = time.monotonic() - self._last_request
        if elapsed < self._rate_limit:
            sleep_time = self._rate_limit - elapsed
            logger.debug("Rate limiter: sleeping %.2fs", sleep_time)
            time.sleep(sleep_time)

    def get(self, url: str, *, bypass_cache: bool = False) -> str:
        """Fetch a URL with caching, rate limiting, and retries."""
        if not bypass_cache:
            cached = self._cache.get(url)
            if cached is not None:
                return cached

        last_exc: Exception | None = None
        for attempt in range(1, 4):
            self._wait_for_rate_limit()
            try:
                headers = {
                    "User-Agent": random.choice(USER_AGENTS),
                    "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
                    "Accept-Language": "en-US,en;q=0.9",
                }
                resp = self._client.get(url, headers=headers)
                resp.raise_for_status()
                self._last_request = time.monotonic()
                html = resp.text
                self._cache.put(url, html)
                return html
            except (httpx.HTTPStatusError, httpx.TransportError) as exc:
                last_exc = exc
                if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code == 429:
                    delay = 2.0 * (2**attempt)
                    logger.warning("429 for %s, retrying in %.1fs", url, delay)
                elif isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code < 500:
                    raise
                else:
                    delay = 2.0 * (2 ** (attempt - 1))
                    logger.warning("Attempt %d/3 failed for %s: %s", attempt, url, exc)
                self._last_request = time.monotonic()
                time.sleep(delay)

        raise last_exc  # type: ignore[misc]

    def close(self) -> None:
        self._client.close()


# ---------------------------------------------------------------------------
# Playwright Browser Scraper (for JS-rendered pages like Torvik)
# ---------------------------------------------------------------------------


class PlaywrightScraper:
    """Headless browser scraper for JS-rendered pages.

    Uses Playwright to render pages that require JavaScript execution
    (e.g., Torvik's browser verification, DataTables).
    """

    def __init__(
        self,
        cache_dir: Path | None = None,
        cache_ttl: int = 86400,
        headless: bool = True,
    ) -> None:
        self._cache = DiskCache(cache_dir or DEFAULT_CACHE_DIR, cache_ttl)
        self._headless = headless
        self._browser = None
        self._playwright = None

    def _ensure_browser(self):
        """Lazy-initialize the Playwright browser with stealth settings."""
        if self._browser is None:
            from playwright.sync_api import sync_playwright

            self._playwright = sync_playwright().start()
            self._browser = self._playwright.chromium.launch(
                headless=self._headless,
                args=["--disable-blink-features=AutomationControlled"],
            )
            self._context = self._browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                viewport={"width": 1920, "height": 1080},
            )
            logger.debug("Playwright browser launched")

    def get(
        self,
        url: str,
        *,
        bypass_cache: bool = False,
        wait_for: str | None = None,
        wait_ms: int = 3000,
    ) -> str:
        """Fetch a URL using a headless browser.

        Args:
            url: Page URL.
            bypass_cache: Skip disk cache.
            wait_for: CSS selector to wait for before capturing HTML.
            wait_ms: Extra milliseconds to wait after page load.

        Returns:
            Fully rendered HTML string.
        """
        if not bypass_cache:
            cached = self._cache.get(url)
            if cached is not None:
                return cached

        self._ensure_browser()
        page = self._context.new_page()
        page.add_init_script(
            'Object.defineProperty(navigator, "webdriver", {get: () => undefined})'
        )
        try:
            logger.debug("Playwright navigating to %s", url)
            page.goto(url, wait_until="networkidle", timeout=30000)

            if wait_for:
                try:
                    page.wait_for_selector(wait_for, timeout=10000)
                except Exception:
                    logger.debug("wait_for selector '%s' not found, continuing", wait_for)

            if wait_ms:
                page.wait_for_timeout(wait_ms)

            html = page.content()
            self._cache.put(url, html)
            logger.debug("Playwright fetched %s (%d bytes)", url, len(html))
            return html
        finally:
            page.close()

    def get_soup(self, url: str, **kwargs) -> BeautifulSoup:
        """Fetch and parse a JS-rendered page."""
        html = self.get(url, **kwargs)
        return parse_html(html)

    def close(self) -> None:
        if hasattr(self, "_context") and self._context:
            self._context.close()
            self._context = None
        if self._browser:
            self._browser.close()
            self._browser = None
        if self._playwright:
            self._playwright.stop()
            self._playwright = None
