"""
Tests for the Write and Read tools.
Verifies that content written via Write can be read back correctly via Read.
"""

import os
import tempfile
import unittest


class TestWriteAndReadTools(unittest.TestCase):
    """Test suite for Write and Read tool functionality."""

    def setUp(self):
        """Create a temporary directory for test files."""
        self.test_dir = tempfile.mkdtemp()
        self.test_file = os.path.join(self.test_dir, "test_write_read.txt")

    def tearDown(self):
        """Clean up temporary files."""
        if os.path.exists(self.test_file):
            os.remove(self.test_file)
        if os.path.exists(self.test_dir):
            os.rmdir(self.test_dir)

    def test_write_and_read_basic(self):
        """Write content, read it back, and verify exact match."""
        content = "Hello, World!"
        # Simulate Write tool: write content to file
        with open(self.test_file, "w", encoding="utf-8") as f:
            f.write(content)

        # Simulate Read tool: read content back
        with open(self.test_file, "r", encoding="utf-8") as f:
            read_content = f.read()

        self.assertEqual(content, read_content, "Read content should match written content")

    def test_write_and_read_multiline(self):
        """Write multiline content and verify read back."""
        content = "Line 1\nLine 2\nLine 3\n"
        with open(self.test_file, "w", encoding="utf-8") as f:
            f.write(content)

        with open(self.test_file, "r", encoding="utf-8") as f:
            read_content = f.read()

        self.assertEqual(content, read_content)
        self.assertEqual(len(content.split("\n")), 4)

    def test_write_and_read_unicode(self):
        """Write and read Unicode content."""
        content = "你好，世界！こんにちは！🎉"
        with open(self.test_file, "w", encoding="utf-8") as f:
            f.write(content)

        with open(self.test_file, "r", encoding="utf-8") as f:
            read_content = f.read()

        self.assertEqual(content, read_content)

    def test_write_and_read_empty(self):
        """Write empty content and read back."""
        content = ""
        with open(self.test_file, "w", encoding="utf-8") as f:
            f.write(content)

        with open(self.test_file, "r", encoding="utf-8") as f:
            read_content = f.read()

        self.assertEqual(content, read_content)
        self.assertEqual(len(read_content), 0)

    def test_write_overwrite(self):
        """Overwrite an existing file and verify new content."""
        # Write initial content
        with open(self.test_file, "w", encoding="utf-8") as f:
            f.write("Initial content")

        # Overwrite with new content
        new_content = "Overwritten content"
        with open(self.test_file, "w", encoding="utf-8") as f:
            f.write(new_content)

        with open(self.test_file, "r", encoding="utf-8") as f:
            read_content = f.read()

        self.assertEqual(read_content, new_content)
        self.assertNotEqual(read_content, "Initial content")

    def test_write_and_read_special_characters(self):
        """Write and read content with special characters."""
        content = "Tab\there\nNewline here\nBackslash\\Quote\"Single'"
        with open(self.test_file, "w", encoding="utf-8") as f:
            f.write(content)

        with open(self.test_file, "r", encoding="utf-8") as f:
            read_content = f.read()

        self.assertEqual(content, read_content)

    def test_write_and_read_large_content(self):
        """Write a large amount of content and verify read back."""
        lines = [f"Line {i}: This is test content for verification." for i in range(1000)]
        content = "\n".join(lines)

        with open(self.test_file, "w", encoding="utf-8") as f:
            f.write(content)

        with open(self.test_file, "r", encoding="utf-8") as f:
            read_content = f.read()

        self.assertEqual(content, read_content)
        self.assertEqual(len(read_content.split("\n")), 1000)

    def test_write_and_read_binary_content(self):
        """Write and read binary content (bytes mode)."""
        content = b"Binary content \x00\x01\x02\xFF"
        with open(self.test_file, "wb") as f:
            f.write(content)

        with open(self.test_file, "rb") as f:
            read_content = f.read()

        self.assertEqual(content, read_content)

    def test_read_nonexistent_file_raises_error(self):
        """Reading a non-existent file should raise FileNotFoundError."""
        nonexistent = os.path.join(self.test_dir, "nonexistent.txt")
        with self.assertRaises(FileNotFoundError):
            with open(nonexistent, "r", encoding="utf-8") as f:
                f.read()

    def test_write_to_nonexistent_directory_raises_error(self):
        """Writing to a non-existent directory should raise FileNotFoundError."""
        bad_path = os.path.join(self.test_dir, "nonexistent_dir", "file.txt")
        with self.assertRaises(FileNotFoundError):
            with open(bad_path, "w", encoding="utf-8") as f:
                f.write("test")

    def test_write_and_read_partial_read(self):
        """Write content and read only a portion using offset/limit semantics."""
        content = "0123456789"
        with open(self.test_file, "w", encoding="utf-8") as f:
            f.write(content)

        # Read with offset=3, limit=4 (characters 3-6)
        with open(self.test_file, "r", encoding="utf-8") as f:
            f.seek(3)
            partial = f.read(4)

        self.assertEqual(partial, "3456")

    def test_write_and_read_verify_no_corruption(self):
        """Write content and verify no data corruption on read."""
        import hashlib
        content = "The quick brown fox jumps over the lazy dog." * 100

        original_hash = hashlib.md5(content.encode("utf-8")).hexdigest()

        with open(self.test_file, "w", encoding="utf-8") as f:
            f.write(content)

        with open(self.test_file, "r", encoding="utf-8") as f:
            read_content = f.read()

        read_hash = hashlib.md5(read_content.encode("utf-8")).hexdigest()

        self.assertEqual(original_hash, read_hash, "MD5 hash should match, indicating no corruption")


if __name__ == "__main__":
    unittest.main()
