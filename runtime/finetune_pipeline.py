"""
Fine-tune Data Pipeline
Collects, cleans, and exports training data from multiple sources
for LLM fine-tuning in Alpaca / ChatML / JSONL formats.

Usage:
    python -m runtime.finetune_pipeline collect --output data/finetune/all.jsonl
    python -m runtime.finetune_pipeline clean --input data/finetune/all.jsonl --output data/finetune/clean.jsonl
    python -m runtime.finetune_pipeline export --input data/finetune/clean.jsonl --format alpaca --output data/finetune/alpaca.json
    python -m runtime.finetune_pipeline stats --input data/finetune/clean.jsonl
"""

import argparse
import json
import os
from collections import Counter
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_ROOT = Path(__file__).parent.parent
_TRAINING_DIR = _ROOT / "data" / "training"
_EVAL_REPORTS_DIR = _ROOT / "data" / "eval" / "reports"
_LESSONS_FILE = _ROOT / "data" / "eval" / "lessons.json"
_FINETUNE_DIR = _ROOT / "data" / "finetune"


def _read_jsonl(path: Path) -> List[Dict[str, Any]]:
    """Read a JSONL file and return list of dicts."""
    entries = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return entries


def _write_jsonl(path: Path, entries: List[Dict[str, Any]]) -> None:
    """Write list of dicts as JSONL."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for entry in entries:
            f.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")


def _similarity(a: str, b: str) -> float:
    """Compute string similarity ratio using SequenceMatcher."""
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


class FinetunePipeline:
    """Collects, cleans, and exports fine-tuning data from multiple sources."""

    def __init__(
        self,
        training_dir: Optional[str] = None,
        eval_reports_dir: Optional[str] = None,
        lessons_file: Optional[str] = None,
    ):
        self.training_dir = Path(training_dir) if training_dir else _TRAINING_DIR
        self.eval_reports_dir = Path(eval_reports_dir) if eval_reports_dir else _EVAL_REPORTS_DIR
        self.lessons_file = Path(lessons_file) if lessons_file else _LESSONS_FILE
        self.data: List[Dict[str, Any]] = []

    # ------------------------------------------------------------------ #
    # Collect
    # ------------------------------------------------------------------ #

    def collect_from_training_dir(self) -> List[Dict[str, Any]]:
        """Read data/training/*.jsonl and convert to instruction-input-output."""
        entries = []
        if not self.training_dir.exists():
            return entries

        for jsonl_file in sorted(self.training_dir.glob("*.jsonl")):
            if jsonl_file.name.startswith("finetune_"):
                # Skip already-exported finetune files
                continue
            for record in _read_jsonl(jsonl_file):
                converted = self._training_record_to_iio(record)
                if converted:
                    entries.append(converted)
        return entries

    def collect_from_eval_reports(self) -> List[Dict[str, Any]]:
        """Read data/eval/reports/*.json and convert task results to iio."""
        entries = []
        if not self.eval_reports_dir.exists():
            return entries

        for json_file in sorted(self.eval_reports_dir.glob("*.json")):
            with open(json_file, "r", encoding="utf-8") as f:
                try:
                    report = json.load(f)
                except json.JSONDecodeError:
                    continue

            results = report.get("results", [])
            for result in results:
                converted = self._eval_result_to_iio(result, report)
                if converted:
                    entries.append(converted)
        return entries

    def collect_from_lessons(self) -> List[Dict[str, Any]]:
        """Read data/eval/lessons.json and convert lessons to iio."""
        entries = []
        if not self.lessons_file.exists():
            return entries

        with open(self.lessons_file, "r", encoding="utf-8") as f:
            try:
                lessons = json.load(f)
            except json.JSONDecodeError:
                return entries

        for lesson in lessons:
            converted = self._lesson_to_iio(lesson)
            if converted:
                entries.append(converted)
        return entries

    def merge_all(self) -> List[Dict[str, Any]]:
        """Collect from all sources, merge, and store in self.data."""
        all_entries = []
        all_entries.extend(self.collect_from_training_dir())
        all_entries.extend(self.collect_from_eval_reports())
        all_entries.extend(self.collect_from_lessons())
        self.data = all_entries
        return self.data

    # ------------------------------------------------------------------ #
    # Converters (private)
    # ------------------------------------------------------------------ #

    @staticmethod
    def _training_record_to_iio(record: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Convert a DataCollector record to instruction-input-output format."""
        task = record.get("task", "").strip()
        if not task:
            return None

        instruction = task
        input_text = record.get("messages_sent_summary", "")

        output_parts = []
        for tc in record.get("tool_calls", []):
            func = tc.get("function", {})
            name = func.get("name", "")
            args = func.get("arguments", "{}")
            output_parts.append(f"CALL {name}({args})")
        for tr in record.get("tool_results", []):
            content = str(tr.get("content", ""))[:300]
            success = tr.get("success", None)
            status = "OK" if success else "FAIL"
            output_parts.append(f"RESULT [{status}]: {content}")

        if not output_parts:
            resp = record.get("llm_response", {})
            output_parts.append(json.dumps(resp, ensure_ascii=False, default=str)[:500])

        output_text = "\n".join(output_parts)
        if not output_text.strip():
            return None

        return {
            "instruction": instruction,
            "input": input_text,
            "output": output_text,
            "source": "training",
            "category": record.get("category", "general"),
        }

    @staticmethod
    def _eval_result_to_iio(
        result: Dict[str, Any], report: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Convert an eval report result to instruction-input-output."""
        title = result.get("title", "").strip()
        if not title:
            return None

        task_id = result.get("task_id", "")
        category = result.get("category", "general")
        difficulty = result.get("difficulty", "medium")
        passed = result.get("passed", False)
        error = result.get("error") or ""
        details = result.get("details", "")

        instruction = f"[Eval Task {task_id}] {title}"
        input_text = f"Category: {category}, Difficulty: {difficulty}"

        if passed:
            output_text = f"Task completed successfully. {details}".strip()
        else:
            output_text = f"Task failed: {error}".strip() if error else f"Task failed. {details}".strip()

        if not output_text.strip():
            return None

        return {
            "instruction": instruction,
            "input": input_text,
            "output": output_text,
            "source": "eval_report",
            "category": category,
        }

    @staticmethod
    def _lesson_to_iio(lesson: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Convert a lesson entry to instruction-input-output."""
        pattern = lesson.get("pattern", "").strip()
        fix = lesson.get("fix", "").strip()
        if not pattern or not fix:
            return None

        category = lesson.get("category", "general")
        lesson_id = lesson.get("id", "")

        instruction = f"[Lesson {lesson_id}] How to handle this pattern: {pattern}"
        input_text = f"Category: {category}, Confidence: {lesson.get('confidence', 'N/A')}"
        output_text = f"Fix: {fix}"

        return {
            "instruction": instruction,
            "input": input_text,
            "output": output_text,
            "source": "lesson",
            "category": category,
        }

    # ------------------------------------------------------------------ #
    # Cleaning
    # ------------------------------------------------------------------ #

    def deduplicate(self, threshold: float = 0.9) -> List[Dict[str, Any]]:
        """Remove duplicates based on instruction similarity.

        Keeps the first occurrence when similarity > threshold.
        """
        unique: List[Dict[str, Any]] = []
        for entry in self.data:
            instr = entry.get("instruction", "")
            is_dup = False
            for existing in unique:
                if _similarity(instr, existing.get("instruction", "")) > threshold:
                    is_dup = True
                    break
            if not is_dup:
                unique.append(entry)
        self.data = unique
        return self.data

    def filter_quality(
        self,
        min_instruction_len: int = 10,
        max_instruction_len: int = 2000,
        min_output_len: int = 5,
        max_output_len: int = 5000,
    ) -> List[Dict[str, Any]]:
        """Filter out low-quality entries.

        Removes entries where:
        - instruction is too short or too long
        - output is too short or too long
        - any required field is missing or not a string
        """
        filtered = []
        for entry in self.data:
            instruction = entry.get("instruction", "")
            output = entry.get("output", "")

            if not isinstance(instruction, str) or not isinstance(output, str):
                continue

            instruction = instruction.strip()
            output = output.strip()

            if len(instruction) < min_instruction_len or len(instruction) > max_instruction_len:
                continue
            if len(output) < min_output_len or len(output) > max_output_len:
                continue

            filtered.append(entry)
        self.data = filtered
        return self.data

    def balance_categories(self, max_per_category: Optional[int] = None) -> List[Dict[str, Any]]:
        """Balance data by category.

        If max_per_category is set, cap each category at that count.
        Otherwise, cap all categories at the size of the smallest category.
        """
        by_category: Dict[str, List[Dict[str, Any]]] = {}
        for entry in self.data:
            cat = entry.get("category", "general")
            by_category.setdefault(cat, []).append(entry)

        if not by_category:
            return self.data

        if max_per_category is None:
            max_per_category = min(len(v) for v in by_category.values())

        balanced = []
        for cat in sorted(by_category.keys()):
            balanced.extend(by_category[cat][:max_per_category])

        self.data = balanced
        return self.data

    def validate_format(self) -> List[Dict[str, Any]]:
        """Keep only entries with valid instruction-input-output format.

        Each entry must have non-empty string 'instruction' and 'output'.
        'input' is optional but must be a string if present.
        """
        valid = []
        for entry in self.data:
            instruction = entry.get("instruction")
            output = entry.get("output")
            inp = entry.get("input")

            if not isinstance(instruction, str) or not instruction.strip():
                continue
            if not isinstance(output, str) or not output.strip():
                continue
            if inp is not None and not isinstance(inp, str):
                continue

            # Normalise: ensure 'input' is always a string
            entry["input"] = inp if isinstance(inp, str) else ""
            valid.append(entry)

        self.data = valid
        return self.data

    # ------------------------------------------------------------------ #
    # Export
    # ------------------------------------------------------------------ #

    def export_jsonl(self, path: str) -> str:
        """Export data as plain JSONL (instruction/input/output per line)."""
        out = Path(path)
        _write_jsonl(out, self.data)
        return str(out)

    def export_alpaca(self, path: str) -> str:
        """Export data in Alpaca format (JSON array of objects)."""
        out = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)
        alpaca = []
        for entry in self.data:
            obj: Dict[str, str] = {
                "instruction": entry.get("instruction", ""),
                "input": entry.get("input", ""),
                "output": entry.get("output", ""),
            }
            alpaca.append(obj)
        with open(out, "w", encoding="utf-8") as f:
            json.dump(alpaca, f, ensure_ascii=False, indent=2)
        return str(out)

    def export_chatml(self, path: str) -> str:
        """Export data in ChatML format (JSONL, each entry is a messages list)."""
        out = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, "w", encoding="utf-8") as f:
            for entry in self.data:
                instruction = entry.get("instruction", "")
                inp = entry.get("input", "")
                output = entry.get("output", "")

                user_content = instruction
                if inp:
                    user_content = f"{instruction}\n\n{inp}"

                messages = [
                    {"role": "system", "content": "You are a helpful coding assistant."},
                    {"role": "user", "content": user_content},
                    {"role": "assistant", "content": output},
                ]
                f.write(json.dumps({"messages": messages}, ensure_ascii=False) + "\n")
        return str(out)

    def generate_stats(self) -> Dict[str, Any]:
        """Generate statistics about the current dataset."""
        total = len(self.data)
        if total == 0:
            return {
                "total": 0,
                "by_source": {},
                "by_category": {},
                "instruction_lengths": {},
                "output_lengths": {},
            }

        sources = Counter(e.get("source", "unknown") for e in self.data)
        categories = Counter(e.get("category", "general") for e in self.data)

        instr_lens = [len(e.get("instruction", "")) for e in self.data]
        output_lens = [len(e.get("output", "")) for e in self.data]

        def _len_stats(lengths: List[int]) -> Dict[str, float]:
            if not lengths:
                return {"min": 0, "max": 0, "avg": 0, "median": 0}
            s = sorted(lengths)
            mid = len(s) // 2
            median = s[mid] if len(s) % 2 else (s[mid - 1] + s[mid]) / 2
            return {
                "min": s[0],
                "max": s[-1],
                "avg": round(sum(s) / len(s), 1),
                "median": median,
            }

        return {
            "total": total,
            "by_source": dict(sources),
            "by_category": dict(categories),
            "instruction_lengths": _len_stats(instr_lens),
            "output_lengths": _len_stats(output_lens),
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }


# ------------------------------------------------------------------ #
# CLI
# ------------------------------------------------------------------ #

def _load_entries(path: str) -> List[Dict[str, Any]]:
    """Load entries from a JSONL or JSON file."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"File not found: {p}")

    if p.suffix == ".json":
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return data
        return []

    return _read_jsonl(p)


def cmd_collect(args: argparse.Namespace) -> None:
    """CLI: collect from all sources."""
    pipeline = FinetunePipeline()
    entries = pipeline.merge_all()
    output = args.output or str(_FINETUNE_DIR / "all.jsonl")
    _write_jsonl(Path(output), entries)
    print(f"Collected {len(entries)} entries -> {output}")


def cmd_clean(args: argparse.Namespace) -> None:
    """CLI: load, clean, and save."""
    entries = _load_entries(args.input)
    pipeline = FinetunePipeline()
    pipeline.data = entries

    before = len(pipeline.data)
    pipeline.validate_format()
    after_fmt = len(pipeline.data)
    pipeline.deduplicate(threshold=args.dedup_threshold)
    after_dedup = len(pipeline.data)
    pipeline.filter_quality()
    after_filter = len(pipeline.data)

    output = args.output or args.input.replace(".jsonl", "_clean.jsonl")
    _write_jsonl(Path(output), pipeline.data)
    print(
        f"Cleaned: {before} -> {after_fmt} (format) -> {after_dedup} (dedup) -> {after_filter} (quality) -> {output}"
    )


def cmd_export(args: argparse.Namespace) -> None:
    """CLI: load and export in the requested format."""
    entries = _load_entries(args.input)
    pipeline = FinetunePipeline()
    pipeline.data = entries

    fmt = args.format.lower()
    if fmt == "alpaca":
        out = args.output or args.input.replace(".jsonl", "_alpaca.json")
        pipeline.export_alpaca(out)
    elif fmt == "chatml":
        out = args.output or args.input.replace(".jsonl", "_chatml.jsonl")
        pipeline.export_chatml(out)
    else:
        out = args.output or args.input.replace(".jsonl", "_out.jsonl")
        pipeline.export_jsonl(out)

    print(f"Exported {len(entries)} entries in {fmt} format -> {out}")


def cmd_stats(args: argparse.Namespace) -> None:
    """CLI: generate and print stats."""
    entries = _load_entries(args.input)
    pipeline = FinetunePipeline()
    pipeline.data = entries

    stats = pipeline.generate_stats()
    print(json.dumps(stats, indent=2, ensure_ascii=False))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fine-tune data pipeline: collect, clean, export, stats"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # collect
    p_collect = sub.add_parser("collect", help="Collect from all data sources")
    p_collect.add_argument("--output", "-o", default=None)

    # clean
    p_clean = sub.add_parser("clean", help="Clean and deduplicate data")
    p_clean.add_argument("--input", "-i", required=True)
    p_clean.add_argument("--output", "-o", default=None)
    p_clean.add_argument("--dedup-threshold", type=float, default=0.9)

    # export
    p_export = sub.add_parser("export", help="Export in training format")
    p_export.add_argument("--input", "-i", required=True)
    p_export.add_argument("--format", "-f", choices=["alpaca", "chatml", "jsonl"], default="jsonl")
    p_export.add_argument("--output", "-o", default=None)

    # stats
    p_stats = sub.add_parser("stats", help="Show dataset statistics")
    p_stats.add_argument("--input", "-i", required=True)

    args = parser.parse_args()

    handlers = {
        "collect": cmd_collect,
        "clean": cmd_clean,
        "export": cmd_export,
        "stats": cmd_stats,
    }
    handlers[args.command](args)


if __name__ == "__main__":
    main()
