"""
Codex-Local Browser Automation
Powered by Playwright - real browser control without Chrome plugins.
Supports Chrome, Firefox, WebKit with full screenshot, DOM access, and automation.
"""

import os
import sys
import json
import time
import asyncio
from pathlib import Path
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field
from concurrent.futures import ThreadPoolExecutor

_root = Path(__file__).parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))


# ─── Playwright Browser ─────────────────────────────────────────────────────

@dataclass
class BrowserResult:
    success: bool
    screenshot_path: Optional[str] = None
    html: Optional[str] = None
    text: Optional[str] = None
    url: Optional[str] = None
    title: Optional[str] = None
    error: Optional[str] = None
    console_logs: List[str] = field(default_factory=list)


class BrowserController:
    """
    Full browser automation via Playwright.
    No Chrome plugin needed - directly controls the browser.

    Usage:
        browser = BrowserController()
        browser.navigate("https://example.com")
        browser.click("button.submit")
        browser.type("input[name='q']", "search query")
        screenshot = browser.screenshot()
        print(browser.text("h1"))
    """

    def __init__(self, browser_type: str = "chromium", headless: bool = True, timeout: int = 30000):
        self.browser_type = browser_type
        self.headless = headless
        self.timeout = timeout
        self._browser: Any = None
        self._context: Any = None
        self._page: Any = None
        self._playwright: Any = None
        self._lock = asyncio.Lock()
        self.console_logs: List[str] = []

    def _init_sync(self):
        """Initialize Playwright and browser synchronously in current thread."""
        if self._playwright is not None:
            return

        from playwright.sync_api import sync_playwright
        self._playwright = sync_playwright().start()

        if self.browser_type == "chromium":
            self._browser = self._playwright.chromium.launch(headless=self.headless)
        elif self.browser_type == "firefox":
            self._browser = self._playwright.firefox.launch(headless=self.headless)
        elif self.browser_type == "webkit":
            self._browser = self._playwright.webkit.launch(headless=self.headless)
        else:
            self._browser = self._playwright.chromium.launch(headless=self.headless)

        self._context = self._browser.new_context(
            viewport={"width": 1280, "height": 800},
            ignore_https_errors=True,
        )
        self._page = self._context.new_page()

        def handle_console(msg):
            self.console_logs.append(f"[{msg.type}] {msg.text}")

        self._page.on("console", handle_console)

    def _ensure_page(self):
        """Lazily initialize browser and page."""
        if self._page is None:
            self._init_sync()

    # ─── Navigation ───────────────────────────────────────────────────────

    def navigate(self, url: str, wait_until: str = "networkidle") -> BrowserResult:
        """Navigate to a URL."""
        self._ensure_page()
        self.console_logs = []

        try:
            self._page.goto(url, timeout=self.timeout, wait_until=wait_until)
            return BrowserResult(
                success=True,
                url=self._page.url,
                title=self._page.title(),
            )
        except Exception as e:
            return BrowserResult(success=False, error=str(e))

    def back(self) -> BrowserResult:
        """Go back in history."""
        self._ensure_page()
        try:
            self._page.go_back()
            return BrowserResult(success=True, url=self._page.url, title=self._page.title())
        except Exception as e:
            return BrowserResult(success=False, error=str(e))

    def forward(self) -> BrowserResult:
        """Go forward in history."""
        self._ensure_page()
        try:
            self._page.go_forward()
            return BrowserResult(success=True, url=self._page.url, title=self._page.title())
        except Exception as e:
            return BrowserResult(success=False, error=str(e))

    # ─── Interaction ─────────────────────────────────────────────────────

    def click(self, selector: str, timeout: int = 10000) -> BrowserResult:
        """Click an element by CSS selector."""
        self._ensure_page()
        try:
            self._page.click(selector, timeout=timeout)
            time.sleep(0.1)
            return BrowserResult(success=True, url=self._page.url, title=self._page.title())
        except Exception as e:
            return BrowserResult(success=False, error=f"Click failed: {e}")

    def double_click(self, selector: str) -> BrowserResult:
        """Double-click an element."""
        self._ensure_page()
        try:
            self._page.dblclick(selector)
            return BrowserResult(success=True, url=self._page.url, title=self._page.title())
        except Exception as e:
            return BrowserResult(success=False, error=str(e))

    def type(self, selector: str, text: str, delay: int = 50, clear_first: bool = True) -> BrowserResult:
        """Type text into an input field."""
        self._ensure_page()
        try:
            if clear_first:
                self._page.fill(selector, "")
            self._page.type(selector, text, delay=delay)
            return BrowserResult(success=True, url=self._page.url, title=self._page.title())
        except Exception as e:
            return BrowserResult(success=False, error=str(e))

    def fill(self, selector: str, text: str) -> BrowserResult:
        """Fill an input without keystroke simulation."""
        self._ensure_page()
        try:
            self._page.fill(selector, text)
            return BrowserResult(success=True)
        except Exception as e:
            return BrowserResult(success=False, error=str(e))

    def press(self, selector: str, key: str, modifiers: Optional[List[str]] = None) -> BrowserResult:
        """Press a keyboard key on an element."""
        self._ensure_page()
        try:
            mods = []
            if modifiers:
                for m in modifiers:
                    if m == "ctrl":
                        mods.append("Control")
                    elif m == "shift":
                        mods.append("Shift")
                    elif m == "alt":
                        mods.append("Alt")
                    elif m == "meta":
                        mods.append("Meta")
            self._page.press(selector, key, modifiers=tuple(mods) if mods else None)
            return BrowserResult(success=True)
        except Exception as e:
            return BrowserResult(success=False, error=str(e))

    def select(self, selector: str, value: str) -> BrowserResult:
        """Select an option from a <select> dropdown."""
        self._ensure_page()
        try:
            self._page.select_option(selector, value)
            return BrowserResult(success=True)
        except Exception as e:
            return BrowserResult(success=False, error=str(e))

    def check(self, selector: str) -> BrowserResult:
        """Check a checkbox or radio button."""
        self._ensure_page()
        try:
            self._page.check(selector)
            return BrowserResult(success=True)
        except Exception as e:
            return BrowserResult(success=False, error=str(e))

    # ─── Content Extraction ─────────────────────────────────────────────

    def text(self, selector: str) -> str:
        """Get text content of an element."""
        self._ensure_page()
        try:
            return self._page.text_content(selector) or ""
        except Exception:
            return ""

    def html(self, selector: Optional[str] = None) -> str:
        """Get innerHTML of an element or full page."""
        self._ensure_page()
        try:
            if selector:
                return self._page.inner_html(selector) or ""
            else:
                return self._page.content()
        except Exception:
            return ""

    def get_attribute(self, selector: str, attr: str) -> Optional[str]:
        """Get an attribute value."""
        self._ensure_page()
        try:
            return self._page.get_attribute(selector, attr)
        except Exception:
            return None

    def url(self) -> str:
        """Get current URL."""
        self._ensure_page()
        return self._page.url if self._page else ""

    def title(self) -> str:
        """Get page title."""
        self._ensure_page()
        return self._page.title() if self._page else ""

    # ─── Screenshot ───────────────────────────────────────────────────────

    def screenshot(self, path: Optional[str] = None, full_page: bool = False,
                   selector: Optional[str] = None) -> BrowserResult:
        """Take a screenshot."""
        self._ensure_page()

        if path is None:
            screenshots_dir = Path("D:/codex-local/screenshots")
            screenshots_dir.mkdir(parents=True, exist_ok=True)
            path = str(screenshots_dir / f"snap_{int(time.time())}.png")

        try:
            if selector:
                el = self._page.locator(selector)
                el.screenshot(path=path)
            elif full_page:
                self._page.screenshot(full_page=True, path=path)
            else:
                self._page.screenshot(path=path)
            return BrowserResult(success=True, screenshot_path=path)
        except Exception as e:
            return BrowserResult(success=False, error=str(e))

    # ─── JavaScript ───────────────────────────────────────────────────────

    def evaluate(self, script: str) -> Any:
        """Execute JavaScript and return result."""
        self._ensure_page()
        try:
            return self._page.evaluate(script)
        except Exception as e:
            return {"error": str(e)}

    # ─── Wait ──────────────────────────────────────────────────────────────

    def wait_for_selector(self, selector: str, timeout: int = 30000, state: str = "visible") -> bool:
        """Wait for an element to appear."""
        self._ensure_page()
        try:
            state_map = {"visible": "visible", "hidden": "hidden", "attached": "attached", "detached": "detached"}
            self._page.wait_for_selector(selector, timeout=timeout, state=state_map.get(state, "visible"))
            return True
        except Exception:
            return False

    def wait_for_navigation(self, timeout: int = 30000, wait_until: str = "networkidle") -> BrowserResult:
        """Wait for navigation to complete."""
        self._ensure_page()
        try:
            self._page.wait_for_load_state(wait_until, timeout=timeout)
            return BrowserResult(success=True, url=self._page.url, title=self._page.title())
        except Exception as e:
            return BrowserResult(success=False, error=str(e))

    def wait_for_timeout(self, ms: int):
        """Wait for a fixed time."""
        time.sleep(ms / 1000)

    # ─── Tabs / Windows ───────────────────────────────────────────────────

    def new_tab(self, url: str = "about:blank") -> BrowserResult:
        """Open a new tab."""
        self._ensure_page()
        try:
            new_page = self._context.new_page()
            new_page.goto(url, timeout=self.timeout)
            return BrowserResult(success=True, url=new_page.url)
        except Exception as e:
            return BrowserResult(success=False, error=str(e))

    # ─── Cleanup ───────────────────────────────────────────────────────────

    def close(self):
        """Close the browser."""
        if self._browser:
            try:
                self._browser.close()
            except Exception:
                pass
            self._browser = None
            self._context = None
            self._page = None

        if self._playwright:
            try:
                self._playwright.stop()
            except Exception:
                pass
            self._playwright = None

    def __del__(self):
        self.close()


# ─── Global singleton ───────────────────────────────────────────────────────

_browser: Optional[BrowserController] = None


def get_browser(headless: bool = True) -> BrowserController:
    global _browser
    if _browser is None:
        _browser = BrowserController(headless=headless)
    return _browser


# ─── CLI test ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    b = BrowserController(headless=False)
    result = b.navigate("https://example.com")
    print(f"Success: {result.success}")
    print(f"URL: {result.url}")
    print(f"Title: {result.title}")
    ss_path = "D:/codex-local/screenshots/test.png"
    b.screenshot(ss_path)
    print(f"Screenshot saved: {ss_path}")
    b.close()