import csv
import os
import pytest
from pathlib import Path

# Fixtures directory
FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures"
INPUT_CSV = FIXTURES_DIR / "sales.csv"
OUTPUT_CSV = Path(__file__).resolve().parent / "filtered_sales_output.csv"

# --- Pipeline functions ---

def read_csv(path: str | Path) -> list[dict]:
    """Read a CSV file and return a list of dictionaries."""
    with open(path, mode="r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return list(reader)

def filter_rows(rows: list[dict], key: str, threshold: float) -> list[dict]:
    """Filter rows where the numeric value of `key` is greater than `threshold`."""
    filtered = []
    for row in rows:
        try:
            if float(row[key]) > threshold:
                filtered.append(row)
        except (ValueError, KeyError):
            continue
    return filtered

def write_csv(rows: list[dict], path: str | Path) -> None:
    """Write a list of dictionaries to a CSV file."""
    if not rows:
        with open(path, mode="w", newline="", encoding="utf-8") as f:
            f.write("")
        return
    fieldnames = list(rows[0].keys())
    with open(path, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

def verify_output(path: str | Path) -> bool:
    """Return True if the output file exists and has at least one data row."""
    if not os.path.exists(path):
        return False
    with open(path, mode="r", newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        rows = list(reader)
        # header + at least one data row
        return len(rows) > 1

# --- Tests ---

class TestE32Integration:
    """Integration test for the full CSV pipeline."""

    def test_full_pipeline(self, tmp_path):
        """
        1. Read sales.csv fixture
        2. Filter rows where amount > 100
        3. Write filtered rows to a temporary output file
        4. Verify the output file exists and contains expected rows
        """
        # 1. Read CSV
        rows = read_csv(INPUT_CSV)
        assert len(rows) > 0, "Input CSV should contain data"

        # 2. Filter rows
        filtered = filter_rows(rows, key="amount", threshold=100.0)
        # Expected rows with amount > 100:
        #   2026-01-01,Widget A,150.00,10
        #   2026-01-02,Widget B,300.00,5
        #   2026-01-04,Widget C,500.00,2
        #   2026-01-05,Widget B,120.00,4
        assert len(filtered) == 4, f"Expected 4 rows with amount > 100, got {len(filtered)}"

        # 3. Write output
        out_file = tmp_path / "filtered_sales_output.csv"
        write_csv(filtered, out_file)

        # 4. Verify output
        assert verify_output(out_file), "Output file should exist and have data rows"

        # Re-read and compare
        output_rows = read_csv(out_file)
        assert len(output_rows) == len(filtered), (
            f"Output row count mismatch: {len(output_rows)} vs {len(filtered)}"
        )
        for orig, written in zip(filtered, output_rows):
            assert orig == written, f"Row mismatch: {orig} != {written}"

    def test_filter_no_match(self, tmp_path):
        """Filter with threshold above all amounts produces an empty file."""
        rows = read_csv(INPUT_CSV)
        filtered = filter_rows(rows, key="amount", threshold=10000.0)
        assert len(filtered) == 0

        out_file = tmp_path / "empty_output.csv"
        write_csv(filtered, out_file)
        assert os.path.exists(out_file), "Empty output file should still be created"

    def test_read_nonexistent(self):
        """Reading a non-existent file raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            read_csv("/nonexistent/path.csv")

    def test_write_and_read_roundtrip(self, tmp_path):
        """Data survives a write→read round-trip."""
        sample = [
            {"date": "2026-02-01", "product": "X", "amount": "99.99", "quantity": "1"},
            {"date": "2026-02-02", "product": "Y", "amount": "1.00", "quantity": "200"},
        ]
        out_file = tmp_path / "roundtrip.csv"
        write_csv(sample, out_file)
        loaded = read_csv(out_file)
        assert loaded == sample


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
