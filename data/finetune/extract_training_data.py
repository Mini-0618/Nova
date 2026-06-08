"""
从 MCR 全家桶提取训练数据
纯规则提取，不需要 LLM，零成本

用法：
    python data/finetune/extract_training_data.py
    python data/finetune/extract_training_data.py --target 10000
"""

import os
import sys
import json
import ast
import re
from pathlib import Path
from typing import List, Dict, Optional

# 扫描目录
SCAN_DIRS = [
    r"D:\ai\AI_WORKSPACE\ECOSYSTEM\runtime",
    r"D:\ai\AI_WORKSPACE\_MIGRATED_FROM_C\ACTIVE\mcr-runtime",
    r"D:\codex-local\runtime",
    r"D:\codex-local\tools",
    r"D:\codex-local\mcp",
    r"D:\codex-local\data\eval",
    r"D:\AIProjects\CyberForge",
    r"D:\ai\KNOWLEDGE",
]

OUTPUT_FILE = Path(r"D:\codex-local\data\finetune\mcr_extracted.jsonl")
OUTPUT_CHATML = Path(r"D:\codex-local\data\finetune\mcr_extracted_chatml.jsonl")


def extract_functions(source: str, filepath: str) -> List[Dict]:
    """从 Python 源码提取函数定义 → 实现对"""
    results = []
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return results

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            func_name = node.name
            if func_name.startswith('_') and not func_name.startswith('__'):
                continue  # 跳过私有函数（但保留 dunder）

            # 提取函数签名
            args = []
            for arg in node.args.args:
                arg_str = arg.arg
                if arg.annotation:
                    arg_str += f": {ast.unparse(arg.annotation)}"
                args.append(arg_str)

            returns = ""
            if node.returns:
                returns = f" -> {ast.unparse(node.returns)}"

            signature = f"def {func_name}({', '.join(args)}){returns}"

            # 提取 docstring
            docstring = ast.get_docstring(node) or ""

            # 提取函数体
            body_lines = []
            for child in node.body:
                if isinstance(child, ast.Expr) and isinstance(child.value, (ast.Constant, ast.Str)):
                    continue  # 跳过 docstring
                try:
                    body_lines.append(ast.unparse(child))
                except:
                    pass

            if not body_lines:
                continue

            body = '\n    '.join(body_lines)

            # 生成 instruction
            if docstring:
                instruction = f"实现以下函数：\n{signature}\n\"\"\"{docstring}\"\"\""
            else:
                instruction = f"实现以下函数：\n{signature}"

            # 生成 output
            output = f"{signature}:\n    {body}"

            results.append({
                'instruction': instruction,
                'input': f"文件: {filepath}",
                'output': output,
                'source': 'function_extraction',
                'quality': 'high' if docstring else 'medium',
            })

    return results


def extract_classes(source: str, filepath: str) -> List[Dict]:
    """从 Python 源码提取类定义"""
    results = []
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return results

    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            class_name = node.name

            # 提取 docstring
            docstring = ast.get_docstring(node) or ""

            # 提取方法列表
            methods = []
            for child in node.body:
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    methods.append(child.name)

            if not methods:
                continue

            # 提取类体（简化版）
            body_lines = []
            for child in node.body:
                try:
                    body_lines.append(ast.unparse(child))
                except:
                    pass

            if not body_lines:
                continue

            body = '\n'.join(body_lines[:20])  # 限制长度

            # 生成 instruction
            if docstring:
                instruction = f"实现一个 Python 类 {class_name}：\n{docstring}"
            else:
                instruction = f"实现一个 Python 类 {class_name}，包含以下方法：{', '.join(methods)}"

            results.append({
                'instruction': instruction,
                'input': f"文件: {filepath}",
                'output': body,
                'source': 'class_extraction',
                'quality': 'high' if docstring else 'medium',
            })

    return results


def extract_tests(source: str, filepath: str) -> List[Dict]:
    """提取测试函数 → 被测代码的对应关系"""
    results = []
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return results

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if not node.name.startswith('test_'):
                continue

            docstring = ast.get_docstring(node) or ""

            body_lines = []
            for child in node.body:
                if isinstance(child, ast.Expr) and isinstance(child.value, (ast.Constant, ast.Str)):
                    continue
                try:
                    body_lines.append(ast.unparse(child))
                except:
                    pass

            if not body_lines:
                continue

            body = '\n    '.join(body_lines)

            # 推断被测函数名
            tested_func = node.name.replace('test_', '').replace('_', ' ')

            instruction = f"为函数 {tested_func} 编写单元测试"
            if docstring:
                instruction += f"：\n{docstring}"

            results.append({
                'instruction': instruction,
                'input': f"文件: {filepath}",
                'output': f"def {node.name}():\n    {body}",
                'source': 'test_extraction',
                'quality': 'high',
            })

    return results


def extract_docstring_code_pairs(source: str, filepath: str) -> List[Dict]:
    """提取文档注释 → 代码对"""
    results = []
    lines = source.split('\n')

    i = 0
    while i < len(lines):
        line = lines[i].strip()

        # 找到注释块
        if line.startswith('#') and len(line) > 5:
            comment_lines = []
            while i < len(lines) and lines[i].strip().startswith('#'):
                comment_lines.append(lines[i].strip().lstrip('# '))
                i += 1

            comment = ' '.join(comment_lines)

            # 找到注释后面的代码
            code_lines = []
            while i < len(lines) and lines[i].strip() and not lines[i].strip().startswith('#'):
                code_lines.append(lines[i])
                i += 1

            if code_lines and len(code_lines) >= 2:
                code = '\n'.join(code_lines)
                if len(code) > 20 and len(code) < 2000:
                    results.append({
                        'instruction': f"根据注释写代码：{comment}",
                        'input': f"文件: {filepath}",
                        'output': code,
                        'source': 'comment_extraction',
                        'quality': 'medium',
                    })
        else:
            i += 1

    return results


def extract_markdown_qa(filepath: str) -> List[Dict]:
    """从 Markdown 文档提取 QA 对"""
    results = []
    try:
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
    except:
        return results

    # 提取标题 → 内容对
    sections = re.split(r'\n#{1,3}\s+', content)
    headers = re.findall(r'#{1,3}\s+(.+)', content)

    for i, header in enumerate(headers):
        if i + 1 < len(sections):
            section_content = sections[i + 1].strip()
            if len(section_content) > 50 and len(section_content) < 2000:
                results.append({
                    'instruction': f"解释以下概念：{header}",
                    'input': f"文件: {filepath}",
                    'output': section_content,
                    'source': 'markdown_extraction',
                    'quality': 'medium',
                })

    return results


def extract_config_patterns(filepath: str) -> List[Dict]:
    """从配置文件提取配置模式"""
    results = []
    try:
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
    except:
        return results

    if filepath.endswith('.json'):
        try:
            data = json.loads(content)
            if isinstance(data, dict) and len(data) > 2:
                results.append({
                    'instruction': f"创建一个配置文件，包含以下设置：{', '.join(list(data.keys())[:5])}",
                    'input': f"文件: {filepath}",
                    'output': json.dumps(data, indent=2, ensure_ascii=False)[:1000],
                    'source': 'config_extraction',
                    'quality': 'low',
                })
        except:
            pass

    return results


def scan_directory(base_dir: str, target_count: int = 10000) -> List[Dict]:
    """扫描目录，提取训练数据"""
    all_samples = []
    base = Path(base_dir)

    if not base.exists():
        print(f"  [SKIP] {base_dir} not found")
        return all_samples

    py_files = list(base.rglob("*.py"))
    md_files = list(base.rglob("*.md"))
    json_files = list(base.rglob("*.json"))

    print(f"  扫描 {base_dir}:")
    print(f"    .py: {len(py_files)}, .md: {len(md_files)}, .json: {len(json_files)}")

    # 处理 Python 文件
    for f in py_files:
        if len(all_samples) >= target_count:
            break
        try:
            source = f.read_text(encoding='utf-8', errors='ignore')
            filepath = str(f)

            all_samples.extend(extract_functions(source, filepath))
            all_samples.extend(extract_classes(source, filepath))
            all_samples.extend(extract_tests(source, filepath))
            all_samples.extend(extract_docstring_code_pairs(source, filepath))
        except:
            pass

    # 处理 Markdown 文件
    for f in md_files:
        if len(all_samples) >= target_count:
            break
        try:
            all_samples.extend(extract_markdown_qa(str(f)))
        except:
            pass

    # 处理 JSON 配置文件
    for f in json_files[:100]:  # 限制 JSON 文件数量
        if len(all_samples) >= target_count:
            break
        try:
            all_samples.extend(extract_config_patterns(str(f)))
        except:
            pass

    return all_samples


def deduplicate(samples: List[Dict]) -> List[Dict]:
    """去重"""
    seen = set()
    unique = []
    for s in samples:
        key = s['instruction'][:80]
        if key not in seen:
            seen.add(key)
            unique.append(s)
    return unique


def filter_quality(samples: List[Dict]) -> List[Dict]:
    """过滤低质量数据"""
    filtered = []
    for s in samples:
        # 跳过太短的
        if len(s.get('output', '')) < 20:
            continue
        # 跳过太长的
        if len(s.get('output', '')) > 3000:
            s['output'] = s['output'][:3000] + '\n# ... (truncated)'
        # 跳过纯导入语句
        if s.get('output', '').strip().startswith('import ') or s.get('output', '').strip().startswith('from '):
            continue
        filtered.append(s)
    return filtered


def main():
    target = 10000
    if '--target' in sys.argv:
        idx = sys.argv.index('--target')
        target = int(sys.argv[idx + 1])

    print(f"目标: {target} 条训练数据")
    print(f"扫描目录: {len(SCAN_DIRS)} 个")
    print()

    all_samples = []
    for dir_path in SCAN_DIRS:
        samples = scan_directory(dir_path, target - len(all_samples))
        all_samples.extend(samples)
        print(f"    提取: {len(samples)} 条 (累计: {len(all_samples)})")
        if len(all_samples) >= target:
            break

    print(f"\n原始数据: {len(all_samples)} 条")

    # 去重
    all_samples = deduplicate(all_samples)
    print(f"去重后: {len(all_samples)} 条")

    # 过滤
    all_samples = filter_quality(all_samples)
    print(f"过滤后: {len(all_samples)} 条")

    # 统计
    sources = {}
    qualities = {}
    for s in all_samples:
        src = s.get('source', 'unknown')
        sources[src] = sources.get(src, 0) + 1
        q = s.get('quality', 'unknown')
        qualities[q] = qualities.get(q, 0) + 1

    print(f"\n来源分布:")
    for src, cnt in sorted(sources.items(), key=lambda x: -x[1]):
        print(f"  {cnt:5d}  {src}")

    print(f"\n质量分布:")
    for q, cnt in sorted(qualities.items(), key=lambda x: -x[1]):
        print(f"  {cnt:5d}  {q}")

    # 写入 Alpaca 格式
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        for s in all_samples:
            record = {
                'instruction': s['instruction'],
                'input': s.get('input', ''),
                'output': s['output'],
            }
            f.write(json.dumps(record, ensure_ascii=False) + '\n')

    # 写入 ChatML 格式
    with open(OUTPUT_CHATML, 'w', encoding='utf-8') as f:
        for s in all_samples:
            chatml = {
                'messages': [
                    {'role': 'system', 'content': 'You are a coding agent. Write clean, well-documented Python code.'},
                    {'role': 'user', 'content': s['instruction']},
                    {'role': 'assistant', 'content': s['output']}
                ]
            }
            f.write(json.dumps(chatml, ensure_ascii=False) + '\n')

    print(f"\n输出文件:")
    print(f"  Alpaca: {OUTPUT_FILE} ({OUTPUT_FILE.stat().st_size / 1024:.0f} KB)")
    print(f"  ChatML: {OUTPUT_CHATML} ({OUTPUT_CHATML.stat().st_size / 1024:.0f} KB)")
    print(f"\n完成！{len(all_samples)} 条训练数据已导出。")


if __name__ == "__main__":
    main()
