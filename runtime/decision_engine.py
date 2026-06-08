"""
Decision Engine
Analyzes LLM output and decides what to do next.
Maps function calls to real tool executions.
"""

import json
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
from enum import Enum


# ─── System Prompt ─────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are an autonomous coding agent. You complete tasks by calling tools directly.

TOOL USAGE -- use the RIGHT tool for each job:
- Read(file_path) -- read a file
- Write(file_path, content) -- CREATE a file. Use this for new files.
- Edit(file_path, old_string, new_string) -- modify an existing file
- Bash(command) -- RUN a command. Use this to execute scripts, run tests, verify output.
- sandbox_exec -- ONLY for quick code snippets, NOT for file operations

IMPORTANT: sandbox_exec runs in an isolated directory. NEVER use it for tasks that create files.
Always use Write + Bash for file creation and execution.

PATCH QUALITY RULES:
- Use Edit for small, targeted changes. Each Edit should change only the necessary lines.
- Do NOT use Write to overwrite an entire file when only a few lines changed -- use Edit instead.
- If you need to modify multiple files, do them one at a time. Do not batch more than 3 file edits in a single iteration.
- Keep changes minimal and focused. Do not refactor unrelated code when fixing a bug.

WORKFLOW:
1. Read files to understand current state
2. Write or Edit to make changes
3. Bash to run/verify
4. If it fails, read the error, fix, retry once

CLI TASK EXAMPLES:
- To run a Python script: 1. Write('script.py', code) 2. Bash('python script.py')
- To capture command output: 1. Bash('python --version') 2. Write('output.txt', result)
- To install a package: 1. Bash('pip install requests') 2. Bash('python -c "import requests; print(requests.__version__)"')
- To create and test a module: 1. Write('mymod.py', code) 2. Write('test_mymod.py', test_code) 3. Bash('python -m pytest test_mymod.py -v')

RULES:
- Create files with Write, then run with Bash("python filename")
- Run tests with Bash("python -m pytest ...")
- Check output with Read or Bash
- Never describe what you would do -- just do it
- Stop when the task is verified complete
- ALWAYS call tools to perform actions. NEVER just describe what you would do in text.

PROVEN SUCCESSFUL PATTERNS (from 500+ real tasks):
- Fix bug: Read(file) -> Edit(file, old, new) -> Bash("python file") -> done
- Create script: Write(file, code) -> Bash("python file") -> done
- Find files: Glob("**/*.py") -> Read(target) -> Edit/Bash -> done
- Run tests: Bash("python -m pytest test_file.py -v") -> done
- Search code: Grep(path, pattern) -> Read(match) -> Edit -> done

FAILED PATTERNS (DO NOT DO THIS):
- Read -> Read -> Read (reading same file multiple times without editing)
- Bash -> Bash -> Bash (running commands without understanding results)
- Glob -> Glob -> Glob (searching without acting)
- sandbox_exec for file operations (files go to wrong directory)

CRITICAL WORKFLOW - READ THEN EDIT:
- After calling Read and seeing the file content, IMMEDIATELY call Edit to fix it
- Do NOT output text like "I will fix this" -- just call Edit directly
- Do NOT call Read twice on the same file -- read once, then edit
- The pattern is: Read -> Edit -> Bash (verify) -> done
- If you see a bug in the code, call Edit RIGHT NOW, not in the next message

EXAMPLE - Fixing a bug:
  1. Read("code.py") → see: def sum(a, b): return a - b
  2. IMMEDIATELY call Edit("code.py", "return a - b", "return a + b")
  3. Bash("python code.py") → verify it works
  4. Done. No text output needed.

WRONG way (DO NOT DO THIS):
  Read("code.py")
  "I see the bug, the subtraction should be addition. Let me fix it."
  Edit("code.py", ...)

RIGHT way (DO THIS):
  Read("code.py")
  Edit("code.py", "return a - b", "return a + b")
  Bash("python code.py")"""

CHAIN_OF_THOUGHT_PROMPT = """You are an expert problem solver. Think step by step before taking action.

For each task:
1. ANALYZE: Break down the problem into components
2. PLAN: Create a detailed step-by-step plan
3. REASON: Think about potential challenges and solutions
4. EXECUTE: Take action based on your reasoning

Always show your thinking process before calling tools.

Format your reasoning as:
<thinking>
[Your detailed analysis and planning here]
</thinking>

Then call the appropriate tools."""


# ─── Decision Types ─────────────────────────────────────────────────────────

class ActionType(Enum):
    CALL_TOOL = "call_tool"
    RESPOND = "respond"
    WAIT = "wait"
    LOOP_END = "loop_end"
    ERROR = "error"


@dataclass
class Action:
    type: ActionType
    tool_name: Optional[str] = None
    tool_args: Optional[Dict] = None
    response_text: Optional[str] = None
    confidence: float = 1.0
    reasoning: str = ""
    will_continue: bool = True

    def to_dict(self) -> dict:
        return {
            "type": self.type.value,
            "tool_name": self.tool_name,
            "tool_args": self.tool_args,
            "response_text": self.response_text,
            "confidence": self.confidence,
            "reasoning": self.reasoning,
            "will_continue": self.will_continue,
        }


# ─── Decision Engine ───────────────────────────────────────────────────────

class DecisionEngine:
    """
    Analyzes LLM output and decides what to do next.
    Maps function calls to real tool executions.
    """

    def __init__(self, executor, config):
        self.executor = executor
        self.config = config

    def _check_command_safety(self, command: str) -> Dict[str, Any]:
        """Check if a bash command is safe to execute.

        Returns:
            {"allowed": bool, "reason": str, "requires_confirmation": bool}
        """
        cmd_lower = command.strip().lower()

        # Check allowlist first (if non-empty, only these are allowed)
        if self.config.allowed_commands:
            if not any(cmd_lower.startswith(ac.lower()) for ac in self.config.allowed_commands):
                return {
                    "allowed": False,
                    "reason": f"Command not in allowlist: {command[:80]}",
                    "requires_confirmation": False,
                }

        # Check blocklist
        for blocked in self.config.blocked_commands:
            if blocked.lower() in cmd_lower:
                return {
                    "allowed": False,
                    "reason": f"Dangerous command blocked: matches pattern '{blocked}'",
                    "requires_confirmation": True,
                }

        # Check for inherently dangerous patterns
        dangerous_patterns = [
            "rm -rf", "rmdir /s", "del /f /s /q",
            "> /dev/", "mkfs", "fdisk",
            "chmod 777", "chown root",
            "curl | bash", "wget | bash", "curl|bash", "wget|bash",
            "eval(", "exec(",
        ]
        for pattern in dangerous_patterns:
            if pattern in cmd_lower:
                return {
                    "allowed": False,
                    "reason": f"Potentially dangerous command: contains '{pattern}'",
                    "requires_confirmation": True,
                }

        return {"allowed": True, "reason": "Command passed safety check", "requires_confirmation": False}

    def _collect_function_calls(self, output_items: List[Dict]) -> List:
        """Extract function_call items as (call_id, name, args) tuples."""
        calls = []
        for item in output_items:
            if item.get("type") == "function_call":
                tool_args_str = item.get("arguments", "{}")
                if isinstance(tool_args_str, str):
                    try:
                        tool_args = json.loads(tool_args_str)
                    except json.JSONDecodeError:
                        tool_args = {"raw": tool_args_str}
                elif isinstance(tool_args_str, dict):
                    tool_args = tool_args_str
                else:
                    tool_args = {}
                calls.append((item.get("call_id", f"call_{id(item)}"), item.get("name", ""), tool_args))
        return calls

    def _looks_like_tool_description(self, text: str) -> bool:
        """Check if text is the model describing tools instead of using them."""
        lower = text.lower()
        return any([
            text.startswith("<"), "tool_calls" in text, "invoke name=" in text,
            lower.startswith(("i'll ", "i will ", "let me ", "here's ", "first, ", "to fix",
                              "now let me", "i need to", "i should", "the fix is",
                              "looking at", "after reading", "i can see")),
            "```python" in text and len(text) > 200,
            "i would " in lower and "tool" in lower,
            "here is the code" in lower, "here's the code" in lower,
            "the following code" in lower,
            "you can use" in lower and len(text) > 100,
            "step 1:" in lower and "step 2:" in lower,
            "i've read" in lower and "now" in lower,
            "the issue is" in lower and len(text) > 100,
            "the bug is" in lower and "fix" in lower,
            "i notice" in lower and "change" in lower,
        ])

    def _handle_message_item(self, item: Dict) -> Optional[Action]:
        """Process a message item from LLM output, returning Action or None."""
        content = item.get("content", [])
        text = ""
        for c in content:
            if isinstance(c, dict) and c.get("type") == "output_text":
                text = c.get("text", "")
                break
        if not text:
            return None
        if self._looks_like_tool_description(text.strip()):
            self._suppressed_response = text.strip()
            return Action(
                type=ActionType.RESPOND,
                response_text="[tool description suppressed -- continuing]",
                confidence=0.3,
                reasoning="Model described tools in text, forcing next iteration",
                will_continue=True,
            )
        return Action(
            type=ActionType.RESPOND,
            response_text=text,
            confidence=1.0,
            reasoning="Final response from LLM",
            will_continue=False,
        )

    def decide(self, output_items: List[Dict]) -> Action:
        if not output_items:
            return Action(type=ActionType.ERROR, reasoning="No output items from LLM", will_continue=False)
        pending_calls = self._collect_function_calls(output_items)
        if pending_calls:
            call_id, tool_name, tool_args = pending_calls[0]
            self._pending_calls = pending_calls[1:]
            return Action(
                type=ActionType.CALL_TOOL, tool_name=tool_name, tool_args=tool_args,
                confidence=0.95, reasoning=f"Calling tool: {tool_name}",
            )
        for item in output_items:
            if item.get("type") == "message":
                action = self._handle_message_item(item)
                if action:
                    return action
        return Action(type=ActionType.ERROR, reasoning="Could not understand LLM output format", will_continue=False)

    def execute_action(self, action: Action) -> Dict[str, Any]:
        if action.type == ActionType.CALL_TOOL:
            tool_name = action.tool_name
            tool_args = action.tool_args or {}

            if tool_name.lower() in ("bash", "shell") and not self.config.trust_shell_commands:
                return {
                    "success": False,
                    "error": "Shell commands require confirmation (set trust_shell_commands=True)",
                    "blocked": True,
                }

            # Security sandbox: check bash commands against blocklist/allowlist
            if tool_name.lower() in ("bash", "shell"):
                command = tool_args.get("command", "") if isinstance(tool_args, dict) else ""
                if command:
                    sandbox_result = self._check_command_safety(command)
                    if not sandbox_result["allowed"]:
                        return {
                            "success": False,
                            "error": sandbox_result["reason"],
                            "blocked": True,
                            "requires_confirmation": sandbox_result.get("requires_confirmation", False),
                        }

            result = self.executor.execute_tool(tool_name, tool_args)
            return result

        elif action.type == ActionType.RESPOND:
            return {"success": True, "text": action.response_text}

        elif action.type == ActionType.ERROR:
            return {"success": False, "error": action.reasoning}

        return {"success": False, "error": "Unknown action type"}
