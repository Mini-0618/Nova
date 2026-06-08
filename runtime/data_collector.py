"""
Training Data Collector
Captures every LLM call during CodexLoop execution for future fine-tuning.
Data is stored as JSONL in data/training/{session_id}.jsonl
"""

import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, Any, List


_DATA_DIR = Path(__file__).parent.parent / "data" / "training"
_log = logging.getLogger(__name__)


def _summarize_messages(messages: List[Dict], max_chars: int = 500) -> str:
    """Create a short summary of the messages sent to the LLM."""
    parts = []
    for msg in messages:
        role = msg.get("role", "unknown")
        content = msg.get("content", "")
        if isinstance(content, list):
            # Handle structured content (e.g., Anthropic format)
            content = " ".join(
                c.get("text", "") for c in content if isinstance(c, dict)
            )
        if content:
            preview = content[:200].replace("\n", " ")
            parts.append(f"{role}: {preview}")
        if msg.get("tool_calls"):
            tc_names = [
                tc.get("function", {}).get("name", "?")
                for tc in msg["tool_calls"]
            ]
            parts.append(f"{role}[tool_calls: {', '.join(tc_names)}]")
    summary = " | ".join(parts)
    return summary[:max_chars]


class DataCollector:
    """Collects LLM interaction data for training/fine-tuning.

    Usage:
        collector = DataCollector(session_id="abc123")
        collector.record(
            task="Create hello.py",
            messages_sent=[...],
            llm_response={...},
            tool_calls=[...],
            tool_results=[...],
            success=True,
            tokens_used=1234,
        )
        collector.save()
    """

    def __init__(self, session_id: str, data_dir: Optional[str] = None):
        self.session_id = session_id
        self.data_dir = Path(data_dir) if data_dir else _DATA_DIR
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.records: List[Dict[str, Any]] = []
        self._file_path = self.data_dir / f"{session_id}.jsonl"

    def record(
        self,
        task: str,
        messages_sent: List[Dict],
        llm_response: Dict[str, Any],
        tool_calls: Optional[List[Dict]] = None,
        tool_results: Optional[List[Dict]] = None,
        success: Optional[bool] = None,
        tokens_used: int = 0,
        iteration: int = 0,
    ) -> Dict[str, Any]:
        """Record one LLM call and its outcome.

        Args:
            task: The user task description
            messages_sent: Messages sent to the LLM
            llm_response: Raw LLM response dict
            tool_calls: List of tool calls made
            tool_results: List of tool results received
            success: Whether this iteration succeeded
            tokens_used: Token count for this call
            iteration: Loop iteration number

        Returns:
            The recorded entry dict
        """
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "session_id": self.session_id,
            "iteration": iteration,
            "task": task[:500],
            "messages_sent_summary": _summarize_messages(messages_sent),
            "messages_sent_count": len(messages_sent),
            "llm_response": _truncate_response(llm_response),
            "tool_calls": tool_calls or [],
            "tool_results": tool_results or [],
            "success": success,
            "tokens_used": tokens_used,
        }
        self.records.append(entry)

        # Append to JSONL file immediately
        try:
            with open(self._file_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")
        except Exception:
            _log.warning("Failed to write training data to %s", self._file_path, exc_info=True)

        return entry

    def save(self) -> str:
        """Flush all records to disk (redundant if record() already writes).

        Returns:
            Path to the JSONL file
        """
        # Already written in record(), but ensure directory exists
        self.data_dir.mkdir(parents=True, exist_ok=True)
        return str(self._file_path)

    def get_records(self) -> List[Dict[str, Any]]:
        """Return all collected records."""
        return list(self.records)

    def export_finetune_format(self, output_path: Optional[str] = None) -> str:
        """Convert collected records to instruction-input-output format for fine-tuning.

        Output format (one JSON object per line):
        {
            "instruction": "task description",
            "input": "system prompt + conversation summary",
            "output": "tool calls and their results"
        }

        Args:
            output_path: Path to write the output file. Defaults to data/training/finetune_{session_id}.jsonl

        Returns:
            Path to the exported file
        """
        if not output_path:
            output_path = str(self.data_dir / f"finetune_{self.session_id}.jsonl")

        entries = []
        for record in self.records:
            # Build instruction from task
            instruction = record.get("task", "")

            # Build input from messages summary
            input_text = record.get("messages_sent_summary", "")

            # Build output from tool calls and results
            output_parts = []
            for tc in record.get("tool_calls", []):
                func = tc.get("function", {})
                name = func.get("name", "")
                args = func.get("arguments", "{}")
                output_parts.append(f"CALL {name}({args})")
            for tr in record.get("tool_results", []):
                content = tr.get("content", "")[:300]
                success = tr.get("success", None)
                status = "OK" if success else "FAIL"
                output_parts.append(f"RESULT [{status}]: {content}")

            if not output_parts:
                # No tool calls — use raw response
                resp = record.get("llm_response", {})
                output_parts.append(json.dumps(resp, ensure_ascii=False, default=str)[:500])

            output_text = "\n".join(output_parts)

            entries.append({
                "instruction": instruction,
                "input": input_text,
                "output": output_text,
            })

        # Write to file
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            for entry in entries:
                f.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")

        return output_path

    @classmethod
    def load(cls, session_id: str, data_dir: Optional[str] = None) -> "DataCollector":
        """Load a collector from an existing JSONL file.

        Args:
            session_id: Session ID to load
            data_dir: Data directory path

        Returns:
            DataCollector with loaded records
        """
        collector = cls(session_id, data_dir)
        file_path = collector.data_dir / f"{session_id}.jsonl"
        if file_path.exists():
            with open(file_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            collector.records.append(json.loads(line))
                        except json.JSONDecodeError:
                            continue
        return collector


def _truncate_response(response: Dict[str, Any], max_chars: int = 2000) -> Dict[str, Any]:
    """Truncate large response fields to keep storage manageable."""
    if not isinstance(response, dict):
        return {"raw": str(response)[:max_chars]}

    truncated = {}
    for key, value in response.items():
        if isinstance(value, str) and len(value) > max_chars:
            truncated[key] = value[:max_chars] + "...[truncated]"
        elif isinstance(value, list) and len(json.dumps(value, default=str)) > max_chars:
            truncated[key] = value[:10]  # Keep first 10 items
        else:
            truncated[key] = value
    return truncated
