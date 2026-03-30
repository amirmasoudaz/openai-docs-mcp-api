from __future__ import annotations

from pathlib import Path

from playwright.sync_api import BrowserContext, Page, sync_playwright


def bootstrap_storage_state(
    storage_state_path: str | Path,
    url: str,
    *,
    interactive: bool = True,
    wait_ms: int = 20_000,
) -> None:
    """
    Opens a real browser session and saves Playwright storage state.

    If the docs site presents an interactive challenge on your network/IP, you’ll
    need to complete it in the opened browser window before closing.
    """
    storage_state_path = Path(storage_state_path)
    storage_state_path.parent.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=False)
        context: BrowserContext = browser.new_context()
        page: Page = context.new_page()
        page.goto(url, wait_until="domcontentloaded")
        page.bring_to_front()
        if interactive:
            print("")
            print("Browser opened for bootstrap.")
            print("If you see a Cloudflare challenge, complete it, then return here.")
            try:
                input("Press Enter to save storage state and close the browser...")
            except (EOFError, KeyboardInterrupt):
                # Non-interactive runners (like CI) won’t have stdin; fall back to time-based wait.
                page.wait_for_timeout(wait_ms)
        else:
            page.wait_for_timeout(wait_ms)
        context.storage_state(path=str(storage_state_path))
        context.close()
        browser.close()


def diagnose_page(
    url: str,
    storage_state_path: str | Path | None = None,
    screenshot_path: str | Path | None = None,
    timeout_ms: int = 60_000,
    headless: bool = True,
    wait_ms: int = 2_000,
    wait_until: str = "domcontentloaded",
) -> dict[str, str | int | bool]:
    storage_state_path = Path(storage_state_path) if storage_state_path else None
    screenshot_path = Path(screenshot_path) if screenshot_path else None

    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=headless)
        context_kwargs: dict = {}
        if storage_state_path and storage_state_path.exists():
            context_kwargs["storage_state"] = str(storage_state_path)
        context = browser.new_context(**context_kwargs)
        page = context.new_page()

        resp = page.goto(url, wait_until=wait_until, timeout=timeout_ms)
        page.wait_for_timeout(wait_ms)
        title = page.title() or ""
        html = page.content()

        lower = (title + "\n" + html).lower()
        challenged = any(
            marker in lower
            for marker in (
                "just a moment",
                "__cf_chl",
                "cf_chl",
                "cf-mitigated",
                "cloudflare",
                "managed challenge",
            )
        )

        if screenshot_path:
            screenshot_path.parent.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(screenshot_path), full_page=True)

        result = {
            "url": url,
            "final_url": page.url,
            "status": int(resp.status) if resp else -1,
            "title": title,
            "html_len": len(html),
            "challenged": challenged,
        }
        context.close()
        browser.close()
        return result
