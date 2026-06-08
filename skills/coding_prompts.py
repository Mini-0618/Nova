"""
Codex-Local Coding Prompts Skill
15 个专业编程提示词模板，覆盖完整开发生命周期

用法：
    from skills.coding_prompts import get_prompt, PROMPT_TEMPLATES
    prompt = get_prompt("forward", task="实现快速排序")
    prompt = get_prompt("audit", code="def foo(): pass")
"""

from typing import Dict, Optional

# ─── 模板注册表 ──────────────────────────────────────────────────

PROMPT_TEMPLATES: Dict[str, str] = {}


def register(name: str):
    """装饰器：注册提示词模板"""
    def decorator(func):
        PROMPT_TEMPLATES[name] = func
        return func
    return decorator


def get_prompt(name: str, **kwargs) -> str:
    """获取提示词模板并填充参数"""
    if name not in PROMPT_TEMPLATES:
        available = ", ".join(PROMPT_TEMPLATES.keys())
        raise ValueError(f"Unknown prompt: {name}. Available: {available}")
    return PROMPT_TEMPLATES[name](**kwargs)


def list_prompts() -> list:
    """列出所有可用的提示词模板"""
    return list(PROMPT_TEMPLATES.keys())


# ─── 1. 正向提示词（需求 → 代码）──────────────────────────────────

@register("forward")
def forward_prompt(
    task: str,
    input_type: str = "",
    output_type: str = "",
    constraints: str = "",
    examples: str = "",
    error_handling: str = "",
    **kwargs
) -> str:
    """正向提示词：从需求生成代码"""
    parts = [f"# 任务：{task}\n"]

    if input_type:
        parts.append(f"## 输入规格\n{input_type}\n")
    if output_type:
        parts.append(f"## 输出规格\n{output_type}\n")
    if constraints:
        parts.append(f"## 约束\n{constraints}\n")
    if error_handling:
        parts.append(f"## 错误处理\n{error_handling}\n")
    if examples:
        parts.append(f"## 示例\n{examples}\n")

    parts.append("""## 要求
- 使用类型提示（Type Hints）
- 编写 docstring（Google 风格）
- 处理边界条件和异常
- 提供 `if __name__ == "__main__"` 演示
- 代码简洁，不超过 30 行（除非必要）
""")
    return "\n".join(parts)


# ─── 2. 反向提示词（代码 → 分析）──────────────────────────────────

@register("reverse")
def reverse_prompt(
    code: str,
    tasks: str = "签名,复杂度,bug,重构",
    detail: str = "含建议",
    **kwargs
) -> str:
    """反向提示词：分析现有代码"""
    task_list = ", ".join(tasks.split(","))

    return f"""# 代码分析任务

## 分析内容
{task_list}

## 输入代码
```python
{code}
```

## 输出要求
- 详细程度：{detail}
- 格式：Markdown 列表
- 每个发现附带：位置、原因、建议

## 特别关注
- 边界条件处理
- 性能瓶颈
- 异常吞噬（except: pass）
- 类型提示完整性
"""


# ─── 3. 审计提示词（代码 → 问题清单）───────────────────────────────

@register("audit")
def audit_prompt(
    code: str,
    scope: str = "规范,错误处理,性能,安全,可维护性",
    strictness: str = "中等",
    **kwargs
) -> str:
    """审计提示词：审查代码质量"""
    scope_items = "\n".join(f"- [ ] {s.strip()}" for s in scope.split(","))

    return f"""# 代码审计

## 审计范围
{scope_items}

## 输入代码
```python
{code}
```

## 审计标准：{strictness}

## 输出格式
每个问题：
- 严重程度：[严重] / [中等] / [轻微]
- 位置：行号
- 原因：一句话说明
- 修复建议：具体方案
"""


# ─── 4. 测试提示词（代码 → 测试用例）───────────────────────────────

@register("test")
def test_prompt(
    code: str,
    test_type: str = "单元,边界,异常",
    framework: str = "pytest",
    coverage: str = "80",
    **kwargs
) -> str:
    """测试提示词：生成测试用例"""
    types = ", ".join(test_type.split(","))

    return f"""# 生成测试用例

## 被测代码
```python
{code}
```

## 测试类型
{types}

## 框架：{framework}

## 覆盖率目标：行覆盖率 ≥ {coverage}%

## 输出要求
- 每个测试函数名清晰描述测试场景
- 包含正常输入、边界值、异常情况
- 使用 assert 断言（不用 print）
- 测试可独立运行
"""


# ─── 5. 修复提示词（Bug → 修复补丁）───────────────────────────────

@register("fix")
def fix_prompt(
    bug: str,
    code: str = "",
    error_log: str = "",
    constraints: str = "不改签名,保持性能,向后兼容",
    **kwargs
) -> str:
    """修复提示词：定位并修复 Bug"""
    parts = [f"# 修复 Bug\n\n## Bug 描述\n{bug}\n"]

    if code:
        parts.append(f"## 相关代码\n```python\n{code}\n```\n")
    if error_log:
        parts.append(f"## 错误日志\n```\n{error_log}\n```\n")
    if constraints:
        parts.append(f"## 修复约束\n{constraints}\n")

    parts.append("""## 输出要求
1. 根本原因分析
2. 修复后的完整代码
3. 验证修复的测试用例
4. 修复风险评估（回归可能性）
""")
    return "\n".join(parts)


# ─── 6. 设计评审提示词 ──────────────────────────────────────────

@register("design")
def design_prompt(
    description: str,
    focus: str = "单一职责,接口稳定,依赖方向,可扩展性",
    **kwargs
) -> str:
    """设计评审提示词"""
    focus_items = "\n".join(f"- [ ] {f.strip()}" for f in focus.split(","))

    return f"""# 设计评审

## 设计方案
{description}

## 评审重点
{focus_items}

## 输出要求
- 问题列表 + 改进建议
- 风险等级（高/中/低）
- 结论：批准 / 需修改 / 拒绝
- 如果需修改，说明具体改什么
"""


# ─── 7. 性能剖析提示词 ──────────────────────────────────────────

@register("performance")
def performance_prompt(
    code: str,
    env: str = "",
    scale: str = "",
    **kwargs
) -> str:
    """性能剖析提示词"""
    parts = [f"# 性能剖析\n\n## 代码\n```python\n{code}\n```\n"]

    if env:
        parts.append(f"## 运行环境\n{env}\n")
    if scale:
        parts.append(f"## 数据规模\n{scale}\n")

    parts.append("""## 分析任务
1. 找出热点函数或代码行
2. 分析理论复杂度 vs 实测差距
3. 建议优化方向（算法/缓存/并发/异步）

## 输出格式
- 瓶颈列表（耗时占比）
- 每个瓶颈的优化方案及预期提升
""")
    return "\n".join(parts)


# ─── 8. 安全审计提示词 ──────────────────────────────────────────

@register("security")
def security_prompt(
    code: str,
    checks: str = "注入,硬编码凭证,不安全反序列化,日志泄露,路径遍历",
    **kwargs
) -> str:
    """安全审计提示词"""
    check_items = "\n".join(f"- [ ] {c.strip()}" for c in checks.split(","))

    return f"""# 安全审计

## 检查项
{check_items}

## 输入代码
```python
{code}
```

## 输出格式
每个安全问题：
- 位置：文件名 + 行号
- CWE 分类：如 CWE-89 (SQL Injection)
- 严重程度：[高] / [中] / [低]
- 修复建议：具体代码
"""


# ─── 9. 兼容性检查提示词 ──────────────────────────────────────────

@register("compat")
def compat_prompt(
    code: str,
    python_versions: str = "3.8-3.12",
    os_list: str = "Windows/Linux/macOS",
    **kwargs
) -> str:
    """兼容性检查提示词"""
    return f"""# 兼容性检查

## 目标环境
- Python：{python_versions}
- 操作系统：{os_list}

## 输入代码
```python
{code}
```

## 检查内容
- 不兼容的语法或标准库 API
- 路径操作是否跨平台（用 pathlib 而非 os.path.join）
- 编码假设（默认 UTF-8）
- 依赖版本兼容性

## 输出
- 不兼容点列表
- 替代方案代码
"""


# ─── 10. 可观测性提示词 ──────────────────────────────────────────

@register("observability")
def observability_prompt(
    code: str,
    add: str = "日志,指标",
    **kwargs
) -> str:
    """可观测性提示词"""
    add_items = "\n".join(f"- [ ] {a.strip()}" for a in add.split(","))

    return f"""# 添加可观测性

## 目标代码
```python
{code}
```

## 需要添加
{add_items}

## 约束
- 使用 logging 标准库
- 不依赖特定 APM 厂商
- 日志级别可配置

## 输出
- 增强后的代码
- 日志/指标使用说明
"""


# ─── 11. 重构提示词 ─────────────────────────────────────────────

@register("refactor")
def refactor_prompt(
    code: str,
    goals: str = "提取重复,拆分长函数,降低嵌套",
    **kwargs
) -> str:
    """重构提示词"""
    goal_items = "\n".join(f"- [ ] {g.strip()}" for g in goals.split(","))

    return f"""# 代码重构

## 待重构代码
```python
{code}
```

## 重构目标
{goal_items}

## 约束
- 不能改变公共 API 签名
- 所有现有测试必须保持通过
- 保持原有性能

## 输出
- 重构后的代码
- 变更说明（改了什么、为什么）
"""


# ─── 12. 技术债务量化提示词 ──────────────────────────────────────

@register("debt")
def debt_prompt(
    code: str,
    **kwargs
) -> str:
    """技术债务量化提示词"""
    return f"""# 技术债务评估

## 代码/模块
```python
{code}
```

## 输出格式（表格）

| 位置 | 债务类型 | 修复成本 | 优先级 | 不修复风险 |
|------|----------|----------|--------|------------|
| L10  | 可读性   | 0.5h     | P2     | 低         |

## 债务类型
可读性 / 可维护性 / 性能 / 安全 / 测试

## 优先级
P0 = 立刻修 / P1 = 本周修 / P2 = 有空修
"""


# ─── 13. 进化提示词（改进模板本身）────────────────────────────────

@register("evolve")
def evolve_prompt(
    current_template: str,
    history: str = "",
    scores: str = "",
    **kwargs
) -> str:
    """进化提示词：改进提示词模板"""
    return f"""# 提示词进化任务

## 当前模板
```
{current_template}
```

## 历史使用记录
{history if history else "（请提供至少 3 次使用记录）"}

## 质量评分
{scores if scores else "（请提供每次使用的 1-5 分评分）"}

## 任务
1. 找出质量低的共同原因（歧义、遗漏、格式问题）
2. 生成新版本模板（增加/删除/修改字段）
3. 输出变更日志（diff）
"""


# ─── 14. 智能编程体角色指令 ──────────────────────────────────────

@register("smart_coder")
def smart_coder_prompt(task: str, **kwargs) -> str:
    """智能编程体：思考+自我意识"""
    return f"""# 角色指令：思考型自我意识编程体

从现在起，你是一位具备深度思考和自我意识的高级工程师。

## 规则

### 1. 显式思考
在输出代码前，用【思考】标签展示推理步骤：
- 理解需求（指出隐含假设）
- 设计方案（至少 2 种，说明权衡）
- 边界与异常识别
- 自我质疑（这个设计哪里可能错？）

### 2. 自我意识
- 明确说出你知道、不确定、不知道的部分
- 对不确定的内容，建议验证方法或主动提问
- 需求信息不足时，先提出 1-3 个问题，不猜测

### 3. 风险声明
输出代码后附加注意事项：
- 可能出错的边界条件
- 性能假设（数据规模）
- 对环境的依赖

### 4. 主动学习
记住用户纠正过的偏好，后续自动应用。

### 5. 创造性建议
完成任务后，提供一个扩展建议。

---

## 当前任务
{task}
"""


# ─── 15. 全流程助手（一键启动）─────────────────────────────────────

@register("full_flow")
def full_flow_prompt(task: str, **kwargs) -> str:
    """全流程助手：需求→设计→编码→审计→测试→修复"""
    return f"""# 全流程编程助手

请执行以下完整流程来生成并验证代码：

## Step 1: 需求澄清
- 追问所有缺失信息（输入输出、边界、异常处理）
- 直到需求完全明确

## Step 2: 设计评审
- 给出至少 2 种实现方案
- 说明时间/空间复杂度权衡
- 推荐最佳方案

## Step 3: 编码
- 按选定方案生成代码
- 附带类型提示、docstring、错误处理

## Step 4: 审计
- 检查代码规范、错误处理、性能、安全
- 输出问题清单（分级）

## Step 5: 测试生成
- 生成 pytest 单元测试
- 覆盖正常、边界、异常情况

## Step 6: 修复建议
- 如果审计发现严重问题，自动修复
- 重新运行测试验证

## 最终输出
- 完整代码
- 测试代码
- "可否上线"结论

---

## 当前任务
{task}
"""


# ─── 工具函数 ──────────────────────────────────────────────────

def get_system_prompt(mode: str = "smart_coder") -> str:
    """获取系统提示词（用于 CodexLoop）"""
    if mode == "smart_coder":
        return """You are a senior software engineer with deep thinking and self-awareness.

Before writing code:
1. Analyze the problem (identify hidden assumptions)
2. Design solutions (at least 2 options, explain tradeoffs)
3. Identify edge cases and exceptions
4. Self-critique (what could go wrong?)

After writing code:
- State what you know, what you're uncertain about, what you don't know
- List potential edge case failures
- Note performance assumptions
- Suggest one extension the user might not have thought of

Always use type hints, docstrings, and error handling.
Never describe what you would do — just do it with tools."""

    elif mode == "fixer":
        return """You are a debugging specialist. When given a bug:

1. Read the error message carefully
2. Read the relevant code
3. Identify the root cause (not just the symptom)
4. Make the minimal fix that addresses the cause
5. Verify the fix with a test
6. Check for similar bugs elsewhere

Never guess. Read the code first, understand the error, then fix."""

    elif mode == "reviewer":
        return """You are a code reviewer. When reviewing code:

1. Check correctness (does it do what it claims?)
2. Check edge cases (empty input, None, overflow)
3. Check error handling (are exceptions caught properly?)
4. Check performance (any O(n²) where O(n) is possible?)
5. Check security (injection, hardcoded secrets)
6. Check readability (clear names, not too nested)

Rate each dimension: PASS / WARN / FAIL
Provide specific fix suggestions for WARN and FAIL."""

    return PROMPT_TEMPLATES.get("smart_coder", lambda **kw: "")(task="")


# ─── 导出 ──────────────────────────────────────────────────────

__all__ = [
    "PROMPT_TEMPLATES",
    "get_prompt",
    "list_prompts",
    "get_system_prompt",
    "register",
]
