"""
Visual Checker - Screenshot comparison and page verification using Playwright.
Wraps BrowserController for visual regression testing.
"""

import os
import sys
import time
from pathlib import Path
from typing import Optional, Tuple

_root = Path(__file__).parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

# Lazy import to avoid hard dependency
_browser_module = None


def _get_browser_module():
    global _browser_module
    if _browser_module is None:
        from tools import browser_automation
        _browser_module = browser_automation
    return _browser_module


class VisualChecker:
    """
    Screenshot comparison and page verification.

    Usage:
        checker = VisualChecker()
        path = checker.take_screenshot("https://example.com")
        similarity = checker.compare_screenshots(path1, path2)
        loaded = checker.check_page_loaded("https://example.com")
        exists = checker.verify_element("h1")
    """

    SIMILARITY_THRESHOLD = 0.95

    def __init__(self, headless: bool = True, browser_type: str = "chromium"):
        self.headless = headless
        self.browser_type = browser_type
        self._browser = None

    def _get_browser(self):
        """Lazily initialize BrowserController."""
        if self._browser is None:
            mod = _get_browser_module()
            self._browser = mod.BrowserController(
                browser_type=self.browser_type,
                headless=self.headless,
            )
        return self._browser

    def take_screenshot(self, url: str, output_path: Optional[str] = None) -> str:
        """
        Navigate to URL and take a screenshot.

        Returns: path to the saved screenshot file.
        """
        browser = self._get_browser()

        if output_path is None:
            screenshots_dir = Path("D:/codex-local/screenshots")
            screenshots_dir.mkdir(parents=True, exist_ok=True)
            output_path = str(screenshots_dir / f"visual_{int(time.time())}.png")

        result = browser.navigate(url)
        if not result.success:
            raise RuntimeError(f"Navigation failed: {result.error}")

        ss_result = browser.screenshot(path=output_path)
        if not ss_result.success:
            raise RuntimeError(f"Screenshot failed: {ss_result.error}")

        return output_path

    def compare_screenshots(self, img1_path: str, img2_path: str) -> float:
        """
        Compare two screenshot images pixel by pixel.

        Returns: similarity ratio 0.0 (completely different) to 1.0 (identical).
        """
        try:
            from PIL import Image
        except ImportError:
            raise ImportError("Pillow is required for image comparison: pip install Pillow")

        img1 = Image.open(img1_path).convert("RGB")
        img2 = Image.open(img2_path).convert("RGB")

        # Resize to same dimensions if different
        if img1.size != img2.size:
            img2 = img2.resize(img1.size)

        # Compare using raw bytes for efficiency
        data1 = img1.tobytes()
        data2 = img2.tobytes()

        if len(data1) == 0:
            return 1.0

        # Each pixel is 3 bytes (RGB)
        total_pixels = len(data1) // 3
        matching = 0
        for i in range(0, min(len(data1), len(data2)), 3):
            if data1[i:i+3] == data2[i:i+3]:
                matching += 1
        return matching / total_pixels if total_pixels else 1.0

    def check_page_loaded(self, url: str, timeout: int = 10) -> bool:
        """
        Navigate to URL and check if page loaded successfully.

        Returns: True if page loaded, False otherwise.
        """
        browser = self._get_browser()
        result = browser.navigate(url)
        if not result.success:
            return False

        # Wait for network idle
        browser._ensure_page()
        try:
            browser._page.wait_for_load_state("domcontentloaded", timeout=timeout * 1000)
            return True
        except Exception:
            return False

    def verify_element(self, selector: str, timeout: int = 5000) -> bool:
        """
        Check if a DOM element exists on the current page.

        Returns: True if element found, False otherwise.
        """
        browser = self._get_browser()
        browser._ensure_page()
        try:
            browser._page.wait_for_selector(selector, timeout=timeout, state="attached")
            return True
        except Exception:
            return False

    def close(self):
        """Close the underlying browser."""
        if self._browser:
            self._browser.close()
            self._browser = None

    def __del__(self):
        self.close()


# ─── CLI Entry Point ─────────────────────────────────────────────────────

def main():
    """CLI: python -m runtime.visual_checker <url> [output_path]"""
    if len(sys.argv) < 2:
        print("Usage: python -m runtime.visual_checker <url> [output_path]")
        sys.exit(1)

    url = sys.argv[1]
    output_path = sys.argv[2] if len(sys.argv) > 2 else None

    checker = VisualChecker(headless=True)
    try:
        path = checker.take_screenshot(url, output_path)
        print(f"Screenshot saved: {path}")

        loaded = checker.check_page_loaded(url)
        print(f"Page loaded: {loaded}")

        h1_exists = checker.verify_element("h1")
        print(f"H1 element found: {h1_exists}")
    finally:
        checker.close()


if __name__ == "__main__":
    main()
