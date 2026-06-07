"""
Codex-Local Windows Control Layer
Provides OS-level control: mouse, keyboard, screenshots, window management, process control.
Uses PyAutoGUI for input simulation and UI Automation for element detection.
"""

import os
import sys
import time
import json
import subprocess
import platform
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass

_root = Path(__file__).parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

# ─── OS Check ──────────────────────────────────────────────────────────────

IS_WINDOWS = platform.system() == "Windows"

if not IS_WINDOWS:
    raise ImportError("win_control requires Windows OS")


# ─── PyAutoGUI setup ─────────────────────────────────────────────────────────

try:
    import pyautogui
    pyautogui.FAILSAFE = True  # Move mouse to corner to abort
    pyautogui.PAUSE = 0.1     # Small pause between actions
    HAS_PYAUTOGUI = True
except ImportError:
    HAS_PYAUTOGUI = False


# ─── UI Automation setup ─────────────────────────────────────────────────────

try:
    import uiautomation as auto
    HAS_UIAUTOMATION = True
except ImportError:
    HAS_UIAUTOMATION = False


# ─── Result Types ─────────────────────────────────────────────────────────────

@dataclass
class WinResult:
    success: bool
    message: str = ""
    data: Optional[Dict] = None
    error: Optional[str] = None


# ─── Screenshot ───────────────────────────────────────────────────────────────

def screenshot(path: Optional[str] = None, region: Optional[Tuple[int,int,int,int]] = None) -> WinResult:
    """
    Take a screenshot. Returns path and basic info.
    If path is None, saves to D:/codex-local/screenshots/ with timestamp.
    If region is (x, y, width, height), captures only that area.
    """
    if not HAS_PYAUTOGUI:
        return WinResult(success=False, error="PyAutoGUI not installed: pip install pyautogui")

    try:
        screenshots_dir = Path("D:/codex-local/screenshots")
        screenshots_dir.mkdir(parents=True, exist_ok=True)

        if path is None:
            path = str(screenshots_dir / f"win_{int(time.time()*1000)}.png")
        else:
            path = str(Path(path))

        if region:
            x, y, w, h = region
            img = pyautogui.screenshot(region=(x, y, w, h))
        else:
            img = pyautogui.screenshot()

        img.save(path)
        size_kb = Path(path).stat().st_size // 1024

        # Get screen size
        screen_w, screen_h = pyautogui.size()

        return WinResult(
            success=True,
            message=f"Screenshot saved: {path} ({size_kb}KB)",
            data={
                "path": path,
                "size_kb": size_kb,
                "screen_width": screen_w,
                "screen_height": screen_h,
                "region": region,
            }
        )
    except Exception as e:
        return WinResult(success=False, error=str(e))


def screenshot_element(window_name: str) -> WinResult:
    """
    Screenshot a specific window by name.
    """
    if not HAS_UIAUTOMATION:
        return WinResult(success=False, error="UI Automation not installed")

    try:
        win = auto.WindowControl(name=window_name)
        if not win.Exists():
            return WinResult(success=False, error=f"Window not found: {window_name}")

        x, y, w, h = win.BoundingRectangle
        return screenshot(region=(x, y, w, h))
    except Exception as e:
        return WinResult(success=False, error=str(e))


# ─── Mouse Control ────────────────────────────────────────────────────────────

def mouse_move(x: int, y: int, duration: float = 0.0) -> WinResult:
    """Move mouse to (x, y). duration=seconds to animate."""
    if not HAS_PYAUTOGUI:
        return WinResult(success=False, error="PyAutoGUI not installed")

    try:
        pyautogui.moveTo(x, y, duration=duration)
        return WinResult(success=True, message=f"Moved to ({x}, {y})")
    except Exception as e:
        return WinResult(success=False, error=str(e))


def mouse_click(x: int, y: int, button: str = "left", clicks: int = 1) -> WinResult:
    """Click at (x, y). button: left/right/middle. clicks: 1 or 2 for double."""
    if not HAS_PYAUTOGUI:
        return WinResult(success=False, error="PyAutoGUI not installed")

    try:
        pyautogui.click(x, y, clicks=clicks, button=button)
        return WinResult(success=True, message=f"Clicked ({x},{y}) {clicks}x with {button} button")
    except Exception as e:
        return WinResult(success=False, error=str(e))


def mouse_double_click(x: int, y: int) -> WinResult:
    """Double click at (x, y)."""
    return mouse_click(x, y, clicks=2)


def mouse_right_click(x: int, y: int) -> WinResult:
    """Right click at (x, y)."""
    return mouse_click(x, y, button="right")


def mouse_drag(start_x: int, start_y: int, end_x: int, end_y: int, duration: float = 0.5) -> WinResult:
    """Drag from (start_x,start_y) to (end_x,end_y)."""
    if not HAS_PYAUTOGUI:
        return WinResult(success=False, error="PyAutoGUI not installed")

    try:
        pyautogui.moveTo(start_x, start_y)
        pyautogui.drag(end_x - start_x, end_y - start_y, duration=duration, button='left')
        return WinResult(success=True, message=f"Dragged ({start_x},{start_y}) → ({end_x},{end_y})")
    except Exception as e:
        return WinResult(success=False, error=str(e))


def mouse_scroll(clicks: int) -> WinResult:
    """Scroll mouse. Positive=up, negative=down."""
    if not HAS_PYAUTOGUI:
        return WinResult(success=False, error="PyAutoGUI not installed")

    try:
        pyautogui.scroll(clicks)
        return WinResult(success=True, message=f"Scrolled {clicks} clicks")
    except Exception as e:
        return WinResult(success=False, error=str(e))


def get_mouse_position() -> WinResult:
    """Get current mouse position."""
    if not HAS_PYAUTOGUI:
        return WinResult(success=False, error="PyAutoGUI not installed")

    try:
        x, y = pyautogui.position()
        return WinResult(success=True, message=f"Mouse at ({x}, {y})", data={"x": x, "y": y})
    except Exception as e:
        return WinResult(success=False, error=str(e))


# ─── Keyboard Control ─────────────────────────────────────────────────────────

def keyboard_type(text: str, interval: float = 0.0) -> WinResult:
    """Type text. interval=seconds between keystrokes."""
    if not HAS_PYAUTOGUI:
        return WinResult(success=False, error="PyAutoGUI not installed")

    try:
        pyautogui.write(text, interval=interval)
        return WinResult(success=True, message=f"Typed {len(text)} chars")
    except Exception as e:
        return WinResult(success=False, error=str(e))


def keyboard_press(key: str) -> WinResult:
    """
    Press a key. Use key names: enter, esc, tab, space, f1-f12,
    ctrl, alt, shift, win, up, down, left, right, etc.
    """
    if not HAS_PYAUTOGUI:
        return WinResult(success=False, error="PyAutoGUI not installed")

    try:
        pyautogui.press(key)
        return WinResult(success=True, message=f"Pressed {key}")
    except Exception as e:
        return WinResult(success=False, error=str(e))


def keyboard_hotkey(*keys) -> WinResult:
    """
    Press a hotkey combination. E.g. keyboard_hotkey('ctrl', 'c') for copy.
    E.g. keyboard_hotkey('win', 'r') for Run dialog.
    """
    if not HAS_PYAUTOGUI:
        return WinResult(success=False, error="PyAutoGUI not installed")

    try:
        pyautogui.hotkey(*keys)
        return WinResult(success=True, message=f"Hotkey: {'+'.join(keys)}")
    except Exception as e:
        return WinResult(success=False, error=str(e))


def keyboard_write(text: str) -> WinResult:
    """Type text with small random interval (natural typing)."""
    if not HAS_PYAUTOGUI:
        return WinResult(success=False, error="PyAutoGUI not installed")

    try:
        pyautogui.write(text)
        return WinResult(success=True, message=f"Wrote {len(text)} chars")
    except Exception as e:
        return WinResult(success=False, error=str(e))


# ─── Window Management ─────────────────────────────────────────────────────────

def window_list() -> WinResult:
    """List all visible windows."""
    if not HAS_UIAUTOMATION:
        return WinResult(success=False, error="UI Automation not installed")

    try:
        windows = []
        for win in auto.TopWindowOrRoot().GetChildren():
            if win.Name:
                x, y, w, h = win.BoundingRectangle
                windows.append({
                    "name": win.Name,
                    "class_name": win.ClassName or "",
                    "rect": {"x": x, "y": y, "width": w - x, "height": h - y},
                    "is_maximized": win.IsMaximized,
                    "is_minimized": win.IsMinimized,
                })
        return WinResult(success=True, message=f"Found {len(windows)} windows", data={"windows": windows})
    except Exception as e:
        return WinResult(success=False, error=str(e))


def window_find(name_contains: str) -> WinResult:
    """Find windows whose name contains the given string."""
    if not HAS_UIAUTOMATION:
        return WinResult(success=False, error="UI Automation not installed")

    try:
        wins = auto.WindowsControl(name=name_contains).GetMatches()
        results = []
        for w in wins:
            x, y, w2, h = w.BoundingRectangle
            results.append({
                "name": w.Name,
                "class_name": w.ClassName or "",
                "rect": {"x": x, "y": y, "width": w2 - x, "height": h - y},
            })
        return WinResult(success=True, message=f"Found {len(results)} windows", data={"windows": results})
    except Exception as e:
        return WinResult(success=False, error=str(e))


def window_activate(name_contains: str) -> WinResult:
    """Activate (bring to front) a window by name."""
    if not HAS_UIAUTOMATION:
        return WinResult(success=False, error="UI Automation not installed")

    try:
        wins = auto.WindowsControl(name=name_contains).GetMatches()
        if not wins:
            return WinResult(success=False, error=f"No window found: {name_contains}")
        wins[0].SetFocus()
        return WinResult(success=True, message=f"Activated: {wins[0].Name}")
    except Exception as e:
        return WinResult(success=False, error=str(e))


def window_close(name_contains: str) -> WinResult:
    """Close a window by sending Alt+F4."""
    wins = auto.WindowsControl(name=name_contains).GetMatches()
    if not wins:
        return WinResult(success=False, error=f"No window: {name_contains}")
    wins[0].SetFocus()
    pyautogui.hotkey('alt', 'f4')
    return WinResult(success=True, message=f"Closed: {name_contains}")


def window_minimize(name_contains: str) -> WinResult:
    """Minimize a window."""
    if not HAS_UIAUTOMATION:
        return WinResult(success=False, error="UI Automation not installed")

    try:
        wins = auto.WindowsControl(name=name_contains).GetMatches()
        if not wins:
            return WinResult(success=False, error=f"No window: {name_contains}")
        wins[0].Minimize()
        return WinResult(success=True, message=f"Minimized: {name_contains}")
    except Exception as e:
        return WinResult(success=False, error=str(e))


# ─── Process Control ───────────────────────────────────────────────────────────

def process_list() -> WinResult:
    """List running processes."""
    try:
        import psutil
        procs = []
        for p in psutil.process_iter(['pid', 'name', 'exe', 'cpu_percent']):
            try:
                info = p.info
                procs.append({
                    "pid": info['pid'],
                    "name": info['name'],
                    "exe": info['exe'],
                    "cpu": info['cpu_percent'],
                })
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        return WinResult(success=True, message=f"Found {len(procs)} processes", data={"processes": procs})
    except ImportError:
        return WinResult(success=False, error="psutil not installed: pip install psutil")


def process_start(path: str, args: str = "") -> WinResult:
    """Start a process. path=full path to .exe, args=command line args."""
    try:
        if args:
            proc = subprocess.Popen([path] + args.split(), start_new_session=True)
        else:
            proc = subprocess.Popen([path], start_new_session=True)
        time.sleep(0.5)
        return WinResult(success=True, message=f"Started PID={proc.pid}", data={"pid": proc.pid})
    except Exception as e:
        return WinResult(success=False, error=str(e))


def process_kill(name_contains: str) -> WinResult:
    """Kill a process by name."""
    try:
        import psutil
        killed = []
        for p in psutil.process_iter(['pid', 'name']):
            try:
                if name_contains.lower() in p.info['name'].lower():
                    p.kill()
                    killed.append(p.info['pid'])
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        return WinResult(success=True, message=f"Killed {len(killed)} processes", data={"killed": killed})
    except ImportError:
        return WinResult(success=False, error="psutil not installed")


# ─── Find Image on Screen ───────────────────────────────────────────────────────

def find_image(image_path: str, confidence: float = 0.8) -> WinResult:
    """
    Find an image on screen. Returns center coordinates if found.
    Use when you have a screenshot of a UI element and need to click it.
    """
    if not HAS_PYAUTOGUI:
        return WinResult(success=False, error="PyAutoGUI not installed")

    try:
        pos = pyautogui.locateOnScreen(image_path, confidence=confidence)
        if pos is None:
            return WinResult(success=False, error=f"Image not found on screen: {image_path}")
        center = pyautogui.center(pos)
        return WinResult(
            success=True,
            message=f"Found at ({center.x}, {center.y})",
            data={"x": center.x, "y": center.y, "region": pos}
        )
    except Exception as e:
        return WinResult(success=False, error=str(e))


def click_image(image_path: str, confidence: float = 0.8) -> WinResult:
    """Find image on screen and click its center."""
    r = find_image(image_path, confidence)
    if not r.success:
        return r
    return mouse_click(r.data["x"], r.data["y"])


# ─── OCR: Read text from screen region ─────────────────────────────────────────

def ocr_region(x: int, y: int, width: int, height: int) -> WinResult:
    """
    OCR text from a screen region. Returns all text found.
    Uses Tesseract via pytesseract.
    """
    try:
        import pytesseract
        from PIL import Image
    except ImportError:
        return WinResult(success=False, error="Need pytesseract and Pillow: pip install pytesseract pillow")

    try:
        # Capture region
        img = pyautogui.screenshot(region=(x, y, width, height))
        text = pytesseract.image_to_string(img)
        return WinResult(
            success=True,
            message=f"OCR read {len(text)} chars",
            data={"text": text.strip(), "chars": len(text.strip())}
        )
    except Exception as e:
        return WinResult(success=False, error=str(e))


# ─── Common Task Recipes ────────────────────────────────────────────────────────

def open_start_menu() -> WinResult:
    """Open Windows Start menu."""
    return keyboard_hotkey('win')


def open_run_dialog() -> WinResult:
    """Open Windows Run dialog (Win+R)."""
    return keyboard_hotkey('win', 'r')


def open_task_manager() -> WinResult:
    """Open Task Manager (Ctrl+Shift+Esc)."""
    return keyboard_hotkey('ctrl', 'shift', 'esc')


def screenshot_and_describe(path: Optional[str] = None) -> WinResult:
    """
    Take screenshot and return basic visual description (text, colors).
    This is the main perception hook for the agent loop.
    """
    r = screenshot(path)
    if not r.success:
        return r

    try:
        from PIL import Image
        img = Image.open(r.data["path"])
        w, h = img.size

        # Get dominant colors
        colors = img.getcolors(maxcolors=1000)
        if colors:
            top_colors = sorted(colors, key=lambda x: x[0], reverse=True)[:5]
            color_summary = [{"rgb": rgb, "count": c} for rgb, c in top_colors]
        else:
            color_summary = []

        r.data["width"] = w
        r.data["height"] = h
        r.data["dominant_colors"] = color_summary

        return WinResult(
            success=True,
            message=f"Screenshot {w}x{h} saved",
            data=r.data
        )
    except Exception as e:
        return WinResult(success=False, error=str(e))


# ─── CLI Test ───────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print(f"PyAutoGUI: {'OK' if HAS_PYAUTOGUI else 'MISSING'}")
    print(f"UI Automation: {'OK' if HAS_UIAUTOMATION else 'MISSING'}")
    print(f"Screen size: {pyautogui.size() if HAS_PYAUTOGUI else 'N/A'}")

    # Quick test
    r = get_mouse_position()
    print(f"Mouse position: {r.message}")

    r = screenshot()
    print(f"Screenshot: {r.message}")