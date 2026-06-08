# Project Card: Codex Local

## MCR Role
Local autonomous coding agent with self-evolution capabilities.

## Kind
tool

## Root
D:\codex-local

## Version
0.2.0

## Tags
tooling, codex, self-evolution, eval, mcp

## Capabilities
- 50-task eval system with scoring
- 20 professional coding prompt templates
- Self-evolution loop (eval -> analyze -> fix -> test -> learn)
- Code quality guard (AST analysis, complexity, security)
- MCP server (9 modules, 45 tools)
- Training data pipeline (auto-collect, clean, export)
- Deep thinker (pre-action reasoning, post-action reflection)
- Evolution engine (version management, tournament selection)
- Multi-file project generator
- MCR v5.0 cognitive loop generator

## Permissions
filesystem.read, filesystem.write, terminal.run, memory.write, network.http

## Integration Contract
- MCR may inspect this project through its manifest
- MCR may run only the declared entrypoint and verify command
- Results must be written to the ecosystem runtime reports
- Destructive operations require explicit user approval

## Verify
python -m pytest tests/ -q --tb=no

## Entrypoints
- python cli.py loop --task "task description"
- python cli.py mcp serve
- python data/eval/run_eval.py --model deepseek-chat
- python skills/self_evolution_loop.py --cycles 3
- python skills/quality_guard.py <file>
