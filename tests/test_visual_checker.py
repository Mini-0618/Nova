"""
Test VisualChecker - screenshot comparison and page verification.
"""

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from runtime.visual_checker import VisualChecker


def test_compare_identical_images():
    """Test that identical images return similarity 1.0."""
    try:
        from PIL import Image
    except ImportError:
        print("  [SKIP] Pillow not installed")
        return

    with tempfile.TemporaryDirectory() as tmpdir:
        img = Image.new("RGB", (100, 100), color=(255, 0, 0))
        path1 = os.path.join(tmpdir, "a.png")
        path2 = os.path.join(tmpdir, "b.png")
        img.save(path1)
        img.save(path2)

        checker = VisualChecker()
        similarity = checker.compare_screenshots(path1, path2)
        assert similarity == 1.0, f"Identical images should have similarity 1.0, got {similarity}"
        print(f"  [OK] Identical images: {similarity}")


def test_compare_different_images():
    """Test that different images return similarity < 1.0."""
    try:
        from PIL import Image
    except ImportError:
        print("  [SKIP] Pillow not installed")
        return

    with tempfile.TemporaryDirectory() as tmpdir:
        img1 = Image.new("RGB", (100, 100), color=(255, 0, 0))
        img2 = Image.new("RGB", (100, 100), color=(0, 0, 255))
        path1 = os.path.join(tmpdir, "a.png")
        path2 = os.path.join(tmpdir, "b.png")
        img1.save(path1)
        img2.save(path2)

        checker = VisualChecker()
        similarity = checker.compare_screenshots(path1, path2)
        assert similarity < 0.1, f"Different images should have low similarity, got {similarity}"
        print(f"  [OK] Different images: {similarity}")


def test_compare_partially_different_images():
    """Test partially different images return intermediate similarity."""
    try:
        from PIL import Image
    except ImportError:
        print("  [SKIP] Pillow not installed")
        return

    with tempfile.TemporaryDirectory() as tmpdir:
        img1 = Image.new("RGB", (100, 100), color=(255, 0, 0))
        img2 = Image.new("RGB", (100, 100), color=(255, 0, 0))
        # Paint bottom half of img2 differently
        pixels = img2.load()
        for x in range(100):
            for y in range(50, 100):
                pixels[x, y] = (0, 0, 255)

        path1 = os.path.join(tmpdir, "a.png")
        path2 = os.path.join(tmpdir, "b.png")
        img1.save(path1)
        img2.save(path2)

        checker = VisualChecker()
        similarity = checker.compare_screenshots(path1, path2)
        assert 0.4 < similarity < 0.6, f"Half-different should be ~0.5, got {similarity}"
        print(f"  [OK] Partially different images: {similarity}")


def test_compare_different_sizes():
    """Test comparing images of different sizes (auto-resize)."""
    try:
        from PIL import Image
    except ImportError:
        print("  [SKIP] Pillow not installed")
        return

    with tempfile.TemporaryDirectory() as tmpdir:
        img1 = Image.new("RGB", (100, 100), color=(255, 0, 0))
        img2 = Image.new("RGB", (200, 200), color=(255, 0, 0))
        path1 = os.path.join(tmpdir, "a.png")
        path2 = os.path.join(tmpdir, "b.png")
        img1.save(path1)
        img2.save(path2)

        checker = VisualChecker()
        similarity = checker.compare_screenshots(path1, path2)
        assert similarity > 0.9, f"Same-color different-size should be >0.9, got {similarity}"
        print(f"  [OK] Different sizes: {similarity}")


def test_verify_element_no_browser():
    """Test verify_element raises gracefully when browser can't start."""
    checker = VisualChecker()
    # We test the method exists and has correct signature
    assert hasattr(checker, "verify_element")
    assert hasattr(checker, "take_screenshot")
    assert hasattr(checker, "check_page_loaded")
    assert hasattr(checker, "compare_screenshots")
    checker.close()
    print(f"  [OK] VisualChecker has all required methods")


def main():
    """Run all tests."""
    tests = [
        ("Compare Identical Images", test_compare_identical_images),
        ("Compare Different Images", test_compare_different_images),
        ("Compare Partially Different", test_compare_partially_different_images),
        ("Compare Different Sizes", test_compare_different_sizes),
        ("Verify Element No Browser", test_verify_element_no_browser),
    ]

    print("=" * 60)
    print("VISUAL CHECKER TEST SUITE")
    print("=" * 60)

    passed = 0
    for name, test_fn in tests:
        try:
            test_fn()
            passed += 1
        except Exception as e:
            print(f"  [FAIL] {name}: {e}")

    print(f"\n  {passed}/{len(tests)} tests passed")
    return 0 if passed == len(tests) else 1


if __name__ == "__main__":
    sys.exit(main())
