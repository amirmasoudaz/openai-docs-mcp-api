from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256

from bs4 import BeautifulSoup
from selenium.common.exceptions import TimeoutException, WebDriverException
import undetected_chromedriver as uc

from .extract import _flatten_syntax_highlighting


@dataclass(frozen=True)
class FetchedPage:
    url: str
    title: str | None
    raw_html: str | None
    main_html: str | None
    main_text: str | None
    content_hash: str | None
    scraped_at: str
    error: str | None


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_text(text: str) -> str:
    return " ".join(text.split())


def _hash_text(text: str) -> str:
    return sha256(text.encode("utf-8")).hexdigest()


class SeleniumChromeFetcher:
    def __init__(self, *, headless: bool = False, mode: str = "undetected") -> None:
        self.headless = headless
        self.mode = mode
        self._driver = None

    def __enter__(self) -> "SeleniumChromeFetcher":
        if self._driver is not None:
            return self

        if self.mode != "undetected":
            raise ValueError("Only mode='undetected' is currently supported.")

        options = uc.ChromeOptions()
        if self.headless:
            options.add_argument("--headless=new")
        options.add_argument("--auto-open-devtools-for-tabs")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--window-size=1440,900")

        self._driver = uc.Chrome(use_subprocess=True, options=options)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()

    def close(self) -> None:
        if self._driver is None:
            return
        try:
            self._driver.quit()
        finally:
            self._driver = None

    def fetch(self, url: str, *, timeout_s: float = 30.0) -> FetchedPage:
        scraped_at = _utc_now_iso()
        if self._driver is None:
            raise RuntimeError("Fetcher not started; use as a context manager.")

        try:
            self._driver.set_page_load_timeout(timeout_s)
            self._driver.get(url)
            raw_html = self._driver.page_source or ""
        except TimeoutException:
            return FetchedPage(
                url=url,
                title=None,
                raw_html=None,
                main_html=None,
                main_text=None,
                content_hash=None,
                scraped_at=scraped_at,
                error=f"Timeout after {timeout_s}s",
            )
        except WebDriverException as e:
            return FetchedPage(
                url=url,
                title=None,
                raw_html=None,
                main_html=None,
                main_text=None,
                content_hash=None,
                scraped_at=scraped_at,
                error=f"WebDriver error: {e}",
            )

        soup = BeautifulSoup(raw_html, "html.parser")
        title_el = soup.find("title")
        title = title_el.get_text(" ", strip=True) if title_el else None

        main = soup.find("main") or soup.find("article")
        if main:
            _flatten_syntax_highlighting(main)
        main_html = str(main) if main else None
        main_text = main.get_text("\n", strip=True) if main else soup.get_text("\n", strip=True)
        main_text = _normalize_text(main_text) if main_text else None
        content_hash = _hash_text(main_text) if main_text else None

        return FetchedPage(
            url=url,
            title=title,
            raw_html=raw_html,
            main_html=main_html,
            main_text=main_text,
            content_hash=content_hash,
            scraped_at=scraped_at,
            error=None,
        )

