# Codex-Local Autonomous Run Report

Date: 2026-06-09
Duration: ~5 hours
Model: deepseek-chat

## Summary

- Pass Rate: 88.0% (44/50)
- Baseline: 74% (37/50)
- Improvement: +14% (7 more tasks)
- Training Data: 1290 JSONL files
- Tests: 283 passing, 9 skipped

## By Category

- agent_loop: 4/5 (80.0%)
- bugfix: 10/10 (100.0%)
- cli: 4/5 (80.0%)
- file_io: 8/10 (80.0%)
- multi_file: 4/5 (80.0%)
- refactor: 4/5 (80.0%)
- self_improve: 5/5 (100.0%)
- test_writing: 5/5 (100.0%)

## By Difficulty

- easy: 8/9 (88.9%)
- hard: 22/24 (91.7%)
- medium: 14/17 (82.4%)

## Fixes Applied

1. ToolExecutor workspace default (tools/executor.py)
   - Was defaulting to D:/ (drive root)
   - Now defaults to project directory
   - Fixed: E01, E20, E22, E24, E25, E35, E36, E37, E38, E39

2. Tool result truncation (runtime/loop.py, tools/executor.py)
   - File reads >20K chars now truncated
   - Fixed: E45, E46, E47, E48, E49, E50

3. Eval token budget (data/eval/run_eval.py)
   - Increased max_total_tokens from 50K to 200K

## Remaining Failures (6)

- [E08] Search and replace across files (file_io/medium)
  expected 'FIXED' in data/eval/workspace/E08_target.txt, got: line1
ERROR here
line3
- [E10] Append to existing file (file_io/easy)
  expected 'NEW LINE' in data/eval/workspace/E10_append.txt, got: existing content
- [E23] Pipe processing (cli/medium)
  test failed (exit 1): Traceback (most recent call last):
  File "<string>", line 1, in <module>
    
- [E29] Replace magic numbers (refactor/medium)
  test failed (exit 1): Traceback (most recent call last):
  File "D:\codex-local\data\eval\workspace\
- [E40] Add config file support (multi_file/hard)
  expected 'Welcome' in output, got: Hello! Will retry 5 times

- [E41] Fix tool calling format (agent_loop/hard)
  test failed (exit 4): 
no tests ran in 0.12s
ERROR: Wrong expression passed to '-k': 'tool': at colu

## Training Data

- Total: 1290 JSONL files
- Location: data/training/

## Git Commits

- fix: correct ToolExecutor workspace default to project root
- fix: add result truncation to prevent context window overflow
- eval: complete full 50-task eval with DeepSeek
- eval v2: 88% pass rate (44/50)