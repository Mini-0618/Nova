# Codex-Local
## 自主运行的AI编程助手

```
D:\codex-local\
├── bridge.py           # API Bridge - OpenAI Responses API兼容层
├── launcher.py         # 服务启动器
├── cli.py              # CLI入口
├── runtime/
│   ├── sandbox.py      # 沙箱执行引擎
│   ├── session.py      # Session管理与持久化
│   └── loop.py         # 自动Loop引擎（核心）
├── tools/
│   └── executor.py     # 工具执行器
├── mcp/
│   ├── server.py       # MCP服务器框架
│   ├── filesystem.py   # 文件系统MCP
│   └── browser.py      # 浏览器控制MCP
└── ui/
    └── console.py      # Web控制台
```

## 快速开始

### 0. 运行自主Loop（一键启动）

```bash
# 最简单的自主运行方式 —— 一句命令完成所有
python -m codex_local.cli loop "你的任务描述"

# 示例：自动创建文件并运行
python -m codex_local.cli loop "在D:/codex-local/test.py中写一个斐波那契数列函数，并运行测试"

# 指定Provider和模型
python -m codex_local.cli loop "分析当前目录结构" --provider deepseek --model deepseek-chat

# 完整服务启动（Bridge + Loop）
python D:\\codex-local\\launcher.py --all --task "你的任务描述"
```

> 自主Loop会自动执行：**接收任务 → 调用LLM → 分析输出 → 决策 → 执行工具 → 循环**，整个过程无需人工干预。

### 1. 配置环境变量

```bash
# 设置Provider和API Key
export CODEX_PROVIDER=deepseek
export CODEX_API_KEY=your_key_here
export CODEX_MODEL=deepseek-chat

# 或使用小米
export CODEX_PROVIDER=xiaomi
export CODEX_API_KEY=your_xiaomi_key
export CODEX_MODEL=mimo-v2.5

# 工作目录
export CODEX_WORKSPACE=D:\
```

### 2. 启动Bridge服务器

```bash
python D:\codex-local\bridge.py
# 运行在 http://127.0.0.1:8787/v1/responses
```

### 3. 运行自动化任务

```bash
python -m codex_local.cli loop "帮我写一个Python文件，在D:/codex-local/test.py输出Hello World"
```

### 4. Web控制台

```bash
pip install flask
python -m codex_local.cli console --port 5000
# 访问 http://127.0.0.1:5000
```

### 5. 启动所有服务

```bash
python D:\codex-local\launcher.py --all --task "你的任务描述"
```

## 支持的Provider

| Provider | Model | API Key Env Var |
|----------|-------|-----------------|
| DeepSeek | deepseek-chat, deepseek-coder | DEEPSEEK_API_KEY |
| XiaoMi | mimo-v2.5 | CODEX_API_KEY |
| Ollama | llama3, qwen2.5 (本地) | 无需API Key |
| Anthropic | claude-sonnet-4-6, claude-opus-4-8 | ANTHROPIC_API_KEY |

## 自动Loop模式

核心引擎 `CodexLoop` 自动执行以下循环：

1. **接收任务** → 2. **调用LLM** → 3. **分析输出** → 4. **决策** → 5. **执行工具** → 6. **循环**

整个过程无需人工确认，工具调用结果会反馈给LLM直到任务完成。

### 运行自动Loop

#### 基本用法

```bash
# 最简单的运行方式
python -m codex_local.cli loop "你的任务描述"

# 示例：创建一个Python文件
python -m codex_local.cli loop "在D:/codex-local/test.py中写一个斐波那契数列函数，并运行测试"
```

#### 指定模型和Provider

```bash
# 使用DeepSeek
python -m codex_local.cli loop "分析当前目录结构" \
    --provider deepseek \
    --model deepseek-chat

# 使用Anthropic Claude
python -m codex_local.cli loop "帮我重构这个项目" \
    --provider anthropic \
    --model claude-sonnet-4-6

# 使用本地Ollama
python -m codex_local.cli loop "解释这个项目的架构" \
    --provider ollama \
    --model llama3
```

#### 多步骤复杂任务

```bash
# 自动完成：分析 → 规划 → 编码 → 测试 → 修复
python -m codex_local.cli loop "
1. 读取D:/codex-local/runtime/loop.py的全部代码
2. 分析其核心逻辑
3. 在D:/codex-local/docs/loop_analysis.md中写一份详细的分析文档
4. 运行一个简单的测试验证功能正常
"
```

#### 使用launcher启动完整服务

```bash
# 启动Bridge + 自动Loop执行任务
python D:\\codex-local\\launcher.py \
    --all \
    --task "扫描D:/codex-local目录，统计代码行数，生成报告到D:/codex-local/report.md"

# 仅启动Loop（不启动Bridge）
python D:\\codex-local\\launcher.py \
    --loop \
    --task "帮我优化runtime/loop.py的性能"
```

#### 通过Bridge API触发Loop

```bash
# 先启动Bridge
python D:\\codex-local\\bridge.py

# 在另一个终端中，通过API触发Loop
curl -X POST http://127.0.0.1:8787/v1/responses \
  -H "Content-Type: application/json" \
  -d '{
    "input": "在D:/codex-local/hello.py中创建一个Flask应用",
    "mode": "auto"
  }'
```

#### 恢复中断的Session

```bash
# 自动恢复上次中断的Loop
python -m codex_local.cli recover

# 指定session文件恢复
python -m codex_local.cli recover --session D:/codex-local/sessions/last_session.json
```

#### 调试模式

```bash
# 显示详细的迭代日志
python -m codex_local.cli loop "修复bug" --verbose

# 限制最大迭代次数（防止无限循环）
python -m codex_local.cli loop "完成这个任务" --max-iterations 20

# 单步模式（每次迭代暂停等待确认）
python -m codex_local.cli loop "逐步完成任务" --step
```

### 信任规则

- `trust_code_execution=True`: 代码执行无需确认
- `trust_file_writes=True`: 文件写入无需确认
- `trust_shell_commands=False`: Shell命令需额外确认（默认关闭）

### 完整示例：自动开发工作流

```bash
# 设置环境
set CODEX_PROVIDER=deepseek
set CODEX_API_KEY=sk-xxxxx
set CODEX_MODEL=deepseek-chat
set CODEX_WORKSPACE=D:/codex-local

# 启动Bridge（后台）
start /B python D:\\codex-local\\bridge.py

# 运行自动Loop - 完成一个完整的开发任务
python -m codex_local.cli loop "
任务：创建一个命令行TODO应用

要求：
1. 在D:/codex-local/todo_app/目录下创建项目
2. 使用Python编写，支持添加、列出、完成、删除TODO项
3. 数据存储使用JSON文件
4. 包含命令行参数解析（argparse）
5. 运行测试确保功能正常
6. 生成README.md使用说明

完成后运行 python D:/codex-local/todo_app/app.py --help 验证
"
```

## 工具列表

- `Read` - 读取文件
- `Write` - 写入文件
- `Edit` - 编辑文件（old_string → new_string）
- `Bash` - 执行Shell命令
- `Glob` / `GlobWalk` - 文件搜索
- `Grep` - 正则搜索
- `TodoWrite` - 任务列表
- `NotebookEdit` - Jupyter Notebook编辑
- `WebFetch` - 抓取网页
- `sandbox_exec` - 在沙箱中执行代码

## Session恢复

每次迭代自动checkpoint，崩溃后可恢复：

```bash
python -m codex_local.cli recover
```

## Token成本估算

| Provider | Input $/1M | Output $/1M |
|----------|-----------|-------------|
| DeepSeek | $0.27 | $1.10 |
| XiaoMi | 约$0.30 | 约$0.30 |
| Ollama | 免费 | 免费 |
| Anthropic | $3.00 | $15.00 |

## MCP集成

MCP服务器可通过STDIO模式集成到Claude Code：

```bash
# 在Claude Code的MCP设置中添加：
# stdio模式下运行 python -m codex_local.mcp.filesystem
```