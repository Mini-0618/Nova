# Codex-Local 准确率提升计划

当前: 74% (37/50)
目标: 92% (46/50)
需要修复: 9 个任务

## 失败模式分析

### no_tool_calls (13 个任务)

- **E01**: Create a file with content
  - 修复: Model must use tools (write_file, run_command) instead of describing code in text
  - 优先级: CRITICAL
- **E08**: Search and replace across files
  - 修复: Model must use tools (write_file, run_command) instead of describing code in text
  - 优先级: CRITICAL
- **E10**: Append to existing file
  - 修复: Model must use tools (write_file, run_command) instead of describing code in text
  - 优先级: CRITICAL
- **E22**: Build a simple argument parser
  - 修复: Model must use tools (write_file, run_command) instead of describing code in text
  - 优先级: CRITICAL
- **E23**: Pipe processing
  - 修复: Model must use tools (write_file, run_command) instead of describing code in text
  - 优先级: CRITICAL
- **E24**: Subprocess with timeout
  - 修复: Model must use tools (write_file, run_command) instead of describing code in text
  - 优先级: CRITICAL
- **E25**: Check exit code
  - 修复: Model must use tools (write_file, run_command) instead of describing code in text
  - 优先级: CRITICAL
- **E29**: Replace magic numbers
  - 修复: Model must use tools (write_file, run_command) instead of describing code in text
  - 优先级: CRITICAL
- **E35**: Test error handling
  - 修复: Model must use tools (write_file, run_command) instead of describing code in text
  - 优先级: CRITICAL
- **E38**: Refactor across files
  - 修复: Model must use tools (write_file, run_command) instead of describing code in text
  - 优先级: CRITICAL
- **E40**: Add config file support
  - 修复: Model must use tools (write_file, run_command) instead of describing code in text
  - 优先级: CRITICAL
- **E41**: Fix tool calling format
  - 修复: Model must use tools (write_file, run_command) instead of describing code in text
  - 优先级: CRITICAL
- **E50**: Design the self-improvement loop
  - 修复: Model must use tools (write_file, run_command) instead of describing code in text
  - 优先级: CRITICAL

## 修复策略

1. **注入经验**: 把 21 条 lessons 注入 system prompt
2. **强制工具调用**: 在 prompt 中明确要求使用 write_file 和 run_command
3. **沙箱验证**: 用 MCR 沙箱验证生成的代码
4. **自动重试**: 失败后自动修复并重试
5. **经验反馈**: 每次成功/失败都更新 lessons
