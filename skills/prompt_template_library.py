# prompt_template_library.py
# Python 3.10+
# 用法：
#   python prompt_template_library.py list
#   python prompt_template_library.py show 1
#   python prompt_template_library.py fill 1 --set 功能目标=实现LRU缓存 --set 输入="capacity:int,key:int,value:int"
#   python prompt_template_library.py export templates.md

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Dict, List, Optional


@dataclass(frozen=True)
class PromptTemplate:
    id: int
    name: str
    category: str
    body: str

    def fields(self) -> List[str]:
        return re.findall(r"{{(.*?)}}", self.body)

    def render(self, values: Dict[str, str]) -> str:
        result = self.body
        for field in self.fields():
            value = values.get(field, f"{{{{{field}}}}}")
            result = result.replace(f"{{{{{field}}}}}", value)
        return result

    def to_markdown(self) -> str:
        return f"## {self.id}. {self.name}\n\n```text\n{self.body}\n```\n"


TEMPLATES: Dict[int, PromptTemplate] = {
    1: PromptTemplate(
        1,
        "正向模板：需求→代码",
        "coding",
        """功能目标：{{功能目标}}
输入：{{输入}}
输出：{{输出}}
约束：{{约束}}
错误处理：{{错误处理}}
资源：{{资源}}
副作用：{{副作用}}
校验：{{校验}}
示例：{{示例}}
依赖：{{依赖}}
交付：{{交付}}
验收：{{验收}}

请直接给出可运行代码。""",
    ),
    2: PromptTemplate(
        2,
        "反向模板：代码→分析",
        "analysis",
        """任务类型：{{任务类型}}
代码：
{{代码}}

输出格式：{{输出格式}}
详细程度：{{详细程度}}
关注点：{{关注点}}

请基于代码本身分析，不要猜测不存在的信息。""",
    ),
    3: PromptTemplate(
        3,
        "审计模板：代码→问题清单",
        "audit",
        """审计范围：{{审计范围}}
代码：
{{代码}}

输出：问题列表（严重/中等/轻微）+ 位置 + 原因 + 修复建议
标准：{{标准}}""",
    ),
    4: PromptTemplate(
        4,
        "测试模板：代码→测试用例",
        "test",
        """目标代码：
{{目标代码}}

测试类型：{{测试类型}}
覆盖率要求：{{覆盖率要求}}
已知示例：{{已知示例}}
框架：{{框架}}
输出：{{输出}}
额外：{{额外}}

请生成可直接运行的测试代码。""",
    ),
    5: PromptTemplate(
        5,
        "修复模板：Bug→修复",
        "fix",
        """Bug描述：{{Bug描述}}
代码：
{{代码}}

约束：{{约束}}
输出：根本原因 / 修复代码 / 验证测试 / 风险评估
可选：{{可选}}""",
    ),
    6: PromptTemplate(
        6,
        "设计评审模板",
        "review",
        """设计方案：
{{设计方案}}

评审重点：{{评审重点}}

输出：问题列表 + 建议 + 风险等级 + 批准与否。""",
    ),
    7: PromptTemplate(
        7,
        "性能剖析模板",
        "performance",
        """代码：
{{代码}}

环境：{{环境}}
任务：{{任务}}

输出：瓶颈列表 + 优化方案 + 预期提升。""",
    ),
    8: PromptTemplate(
        8,
        "安全审计模板",
        "security",
        """检查项：注入 / 硬编码凭证 / 不安全反序列化 / 日志泄露 / ReDoS / 路径遍历 / 不安全配置

代码：
{{代码}}

输出：位置 + CWE + 严重程度 + 修复建议。""",
    ),
    9: PromptTemplate(
        9,
        "兼容性检查模板",
        "compatibility",
        """目标环境：{{目标环境}}
检查：语法 / 标准库 / 路径操作 / 编码假设

代码：
{{代码}}

输出：不兼容点 + 替代方案。""",
    ),
    10: PromptTemplate(
        10,
        "可观测性模板",
        "observability",
        """目标代码：
{{目标代码}}

添加：结构化日志 / 指标埋点 / 追踪上下文
约束：只用 logging，不依赖厂商

输出：增强代码 + 使用说明。""",
    ),
    11: PromptTemplate(
        11,
        "重构模板",
        "refactor",
        """代码：
{{代码}}

目标：{{目标}}
约束：{{约束}}

输出：重构代码 + 变更说明。""",
    ),
    12: PromptTemplate(
        12,
        "技术债务模板",
        "debt",
        """代码：
{{代码}}

输出：债务类型 / 修复成本 / 优先级 / 不修复风险，使用表格。""",
    ),
    13: PromptTemplate(
        13,
        "进化模板：改进模板本身",
        "meta",
        """当前模板：
{{当前模板}}

历史使用记录：
{{历史使用记录}}

任务：找共性问题 → 生成新版模板 → 输出变更日志
可选：{{可选}}""",
    ),
    14: PromptTemplate(
        14,
        "智能编程体角色指令",
        "role",
        """角色：思考型编程助手

规则：
1. 先理解需求，再给方案。
2. 明确说明知道 / 不确定 / 不知道。
3. 信息不足时主动指出缺口。
4. 输出代码后附注意事项：边界 / 性能假设 / 依赖。
5. 记住我纠正过的偏好。
6. 提供一个扩展想法。
7. 不展示隐藏推理，只输出可读的分析摘要。

当前任务：
{{当前任务}}""",
    ),
    15: PromptTemplate(
        15,
        "全流程助手：一键启动",
        "workflow",
        """全流程指令：

执行：
1. 需求澄清
2. 设计评审
3. 编码
4. 审计
5. 测试生成
6. 修复建议
7. 可否上线结论

当前需求：
{{当前需求}}

请分段输出，最后给出"可否上线"。""",
    ),
}


def list_templates() -> None:
    for template in TEMPLATES.values():
        print(f"{template.id:02d}. {template.name} [{template.category}]")


def show_template(template_id: int) -> None:
    template = get_template(template_id)
    print(template.body)


def get_template(template_id: int) -> PromptTemplate:
    template = TEMPLATES.get(template_id)
    if template is None:
        raise SystemExit(f"模板不存在：{template_id}")
    return template


def parse_set_args(items: Optional[List[str]]) -> Dict[str, str]:
    values: Dict[str, str] = {}
    if not items:
        return values

    for item in items:
        if "=" not in item:
            raise SystemExit(f"--set 格式错误，应为 key=value：{item}")
        key, value = item.split("=", 1)
        key = key.strip()
        if not key:
            raise SystemExit(f"--set 的 key 不能为空：{item}")
        values[key] = value.strip()

    return values


def fill_template(template_id: int, set_items: Optional[List[str]]) -> None:
    template = get_template(template_id)
    values = parse_set_args(set_items)
    print(template.render(values))


def search_templates(keyword: str) -> None:
    keyword_lower = keyword.lower()
    matched = []

    for template in TEMPLATES.values():
        haystack = f"{template.name} {template.category} {template.body}".lower()
        if keyword_lower in haystack:
            matched.append(template)

    if not matched:
        print("没有找到匹配模板。")
        return

    for template in matched:
        print(f"{template.id:02d}. {template.name} [{template.category}]")


def export_markdown(path: str) -> None:
    output = "# 编程提示词模板库\n\n"
    for template in TEMPLATES.values():
        output += template.to_markdown() + "\n"

    Path(path).write_text(output, encoding="utf-8")
    print(f"已导出：{path}")


def export_json(path: str) -> None:
    data = [asdict(template) for template in TEMPLATES.values()]
    Path(path).write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"已导出：{path}")


def interactive_fill(template_id: int) -> None:
    template = get_template(template_id)
    values: Dict[str, str] = {}

    print(f"正在填写模板：{template.name}")
    print("-" * 40)

    for field in template.fields():
        values[field] = input(f"{field}：").strip()

    print("\n生成结果：")
    print("=" * 40)
    print(template.render(values))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="prompt_template_library",
        description="编程提示词模板库 CLI",
    )

    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list", help="列出所有模板")

    show = sub.add_parser("show", help="查看模板")
    show.add_argument("id", type=int)

    fill = sub.add_parser("fill", help="填充模板")
    fill.add_argument("id", type=int)
    fill.add_argument(
        "--set",
        action="append",
        help="设置字段，格式：字段=内容，可重复使用",
    )

    interactive = sub.add_parser("interactive", help="交互式填写模板")
    interactive.add_argument("id", type=int)

    search = sub.add_parser("search", help="搜索模板")
    search.add_argument("keyword")

    export_md = sub.add_parser("export", help="导出为 Markdown")
    export_md.add_argument("path")

    export_j = sub.add_parser("export-json", help="导出为 JSON")
    export_j.add_argument("path")

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "list":
        list_templates()
    elif args.command == "show":
        show_template(args.id)
    elif args.command == "fill":
        fill_template(args.id, args.set)
    elif args.command == "interactive":
        interactive_fill(args.id)
    elif args.command == "search":
        search_templates(args.keyword)
    elif args.command == "export":
        export_markdown(args.path)
    elif args.command == "export-json":
        export_json(args.path)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
