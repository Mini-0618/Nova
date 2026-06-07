"""
Codex-Local Data Cleaner
数据清洗工具集：加载、质量检测、去重、空值处理、统计分析、报告生成。
"""

import os
import sys
import json
import subprocess
from pathlib import Path
from typing import Dict, Optional, Any, List
from dataclasses import dataclass, field

_root = Path(__file__).parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))


# ─── DataLoader ────────────────────────────────────────────────────────────

def load_data(file_path: str) -> Dict[str, Any]:
    """
    加载 CSV 或 Excel 文件，返回基本信息。
    支持 .csv, .xlsx, .xls
    """
    if not os.path.exists(file_path):
        return {"status": "error", "message": f"文件不存在：{file_path}"}

    ext = os.path.splitext(file_path)[1].lower()

    try:
        import pandas as pd
        if ext == ".csv":
            try:
                df = pd.read_csv(file_path, encoding="utf-8")
            except UnicodeDecodeError:
                df = pd.read_csv(file_path, encoding="gbk")
        elif ext in (".xlsx", ".xls"):
            df = pd.read_excel(file_path)
        else:
            return {"status": "error", "message": f"不支持的格式：{ext}，请使用 .csv 或 .xlsx"}

        # 保存临时文件供后续步骤使用
        tmp_dir = Path(os.environ.get("CODEX_DATA", "D:/codex-local/data"))
        tmp_dir.mkdir(parents=True, exist_ok=True)
        tmp_path = str(tmp_dir / "loaded_data.csv")
        df.to_csv(tmp_path, index=False, encoding="utf-8")

        return {
            "status": "success",
            "rows": len(df),
            "cols": len(df.columns),
            "columns": list(df.columns),
            "dtypes": {k: str(v) for k, v in df.dtypes.to_dict().items()},
            "tmp_path": tmp_path,
            "shape": {"rows": len(df), "cols": len(df.columns)},
        }

    except Exception as e:
        return {"status": "error", "message": str(e)}


# ─── QualityChecker ─────────────────────────────────────────────────────────

def quality_check(file_path: str) -> Dict[str, Any]:
    """
    扫描数据质量问题：空值、重复行、异常值（IQR方法）
    """
    try:
        import pandas as pd

        if not os.path.exists(file_path):
            return {"status": "error", "message": f"文件不存在：{file_path}"}

        df = pd.read_csv(file_path)

        # 空值统计
        null_counts = df.isnull().sum()
        null_issues = [
            {
                "column": str(col),
                "null_count": int(cnt),
                "null_pct": round(cnt / len(df) * 100, 1) if len(df) > 0 else 0
            }
            for col, cnt in null_counts.items() if cnt > 0
        ]

        # 重复行
        dup_count = int(df.duplicated().sum())

        # 异常值检测（数值列的 IQR 方法）
        outlier_issues = []
        for col in df.select_dtypes(include="number").columns:
            q1 = df[col].quantile(0.25)
            q3 = df[col].quantile(0.75)
            iqr = q3 - q1
            if iqr == 0:
                continue
            lower = q1 - 1.5 * iqr
            upper = q3 + 1.5 * iqr
            outliers = df[(df[col] < lower) | (df[col] > upper)]
            if len(outliers) > 0:
                outlier_issues.append({
                    "column": str(col),
                    "count": len(outliers),
                    "count_pct": round(len(outliers) / len(df) * 100, 1),
                    "range": f"[{lower:.4f}, {upper:.4f}]"
                })

        issues_count = len(null_issues) + (1 if dup_count > 0 else 0) + len(outlier_issues)

        # 质量评分（0-100）
        score = 100
        if len(df) > 0:
            if null_issues:
                total_null_pct = sum(i["null_pct"] for i in null_issues) / len(null_issues)
                score -= min(total_null_pct * 0.5, 30)
            if dup_count > 0:
                score -= min(dup_count / len(df) * 100 * 0.5, 25)
            if outlier_issues:
                avg_outlier_pct = sum(i["count_pct"] for i in outlier_issues) / len(outlier_issues)
                score -= min(avg_outlier_pct * 0.3, 20)
        score = max(0, round(score, 1))

        return {
            "status": "success",
            "quality_score": score,
            "total_issues": issues_count,
            "duplicate_rows": dup_count,
            "null_columns": null_issues,
            "outlier_columns": outlier_issues,
            "rows_total": len(df),
            "has_issues": issues_count > 0,
        }

    except Exception as e:
        return {"status": "error", "message": str(e)}


# ─── DataCleaner ────────────────────────────────────────────────────────────

def clean_data(
    file_path: str,
    output_path: Optional[str] = None,
    remove_duplicates: bool = True,
    fill_numeric_nulls: float = 0.0,
    fill_string_nulls: str = "",
    strip_whitespace: bool = True,
    rename_columns: bool = True,
) -> Dict[str, Any]:
    """
    执行数据清洗流程。
    默认规则：去重、空值填0/空字符串、去除首尾空格、列名标准化
    """
    try:
        import pandas as pd

        if not os.path.exists(file_path):
            return {"status": "error", "message": f"文件不存在：{file_path}"}

        df = pd.read_csv(file_path)
        stats = {}

        # 1. 标准化列名
        if rename_columns:
            original_cols = list(df.columns)
            df.columns = [c.strip().lower().replace(" ", "_").replace("\n", "_") for c in df.columns]
            stats["cols_renamed"] = sum(a != b for a, b in zip(original_cols, df.columns))
            stats["original_columns"] = original_cols
            stats["new_columns"] = list(df.columns)

        # 2. 删除重复行
        if remove_duplicates:
            before = len(df)
            df.drop_duplicates(inplace=True)
            df.reset_index(drop=True, inplace=True)
            stats["dup_removed"] = before - len(df)

        # 3. 填充空值
        null_before = int(df.isnull().sum().sum())
        for col in df.columns:
            if df[col].dtype in ("int64", "float64"):
                df.loc[:, col] = df[col].fillna(fill_numeric_nulls)
            else:
                df.loc[:, col] = df[col].fillna(fill_string_nulls)
        stats["nulls_filled"] = null_before - int(df.isnull().sum().sum())

        # 4. 去除字符串首尾空格
        if strip_whitespace:
            for col in df.select_dtypes(include="object").columns:
                df[col] = df[col].astype(str).str.strip()
            stats["whitespace_stripped"] = True

        # 保存
        if output_path is None:
            out_dir = Path(os.environ.get("CODEX_DATA", "D:/codex-local/data"))
            out_dir.mkdir(parents=True, exist_ok=True)
            output_path = str(out_dir / "cleaned_data.csv")

        df.to_csv(output_path, index=False, encoding="utf-8")
        stats["output_path"] = output_path
        stats["rows_after"] = len(df)
        stats["cols_after"] = len(df.columns)

        return {
            "status": "success",
            **stats
        }

    except Exception as e:
        return {"status": "error", "message": str(e)}


# ─── StatsCalculator ────────────────────────────────────────────────────────

def calc_stats(file_path: str) -> Dict[str, Any]:
    """
    计算数据集的统计信息：数值列的描述性统计 + 分类列的分布
    """
    try:
        import pandas as pd
        import numpy as np

        if not os.path.exists(file_path):
            return {"status": "error", "message": f"文件不存在：{file_path}"}

        df = pd.read_csv(file_path)

        # 数值列统计
        numeric_stats = {}
        for col in df.select_dtypes(include="number").columns:
            s = df[col].dropna()
            if len(s) == 0:
                continue
            numeric_stats[str(col)] = {
                "count": len(s),
                "mean": round(float(s.mean()), 4),
                "std": round(float(s.std()), 4),
                "min": float(s.min()),
                "max": float(s.max()),
                "p25": float(s.quantile(0.25)),
                "p50": float(s.quantile(0.50)),
                "p75": float(s.quantile(0.75)),
            }

        # 分类列统计（只显示前10个值）
        categorical_stats = {}
        for col in df.select_dtypes(include="object").columns:
            s = df[col].dropna()
            if len(s) == 0:
                continue
            top_values = s.value_counts().head(10)
            categorical_stats[str(col)] = {
                "count": len(s),
                "unique": int(s.nunique()),
                "top_values": {str(k): int(v) for k, v in top_values.items()},
            }

        # 相关性矩阵（数值列之间）
        corr_matrix = None
        numeric_cols = df.select_dtypes(include="number").columns
        if len(numeric_cols) > 1:
            corr = df[numeric_cols].corr()
            corr_matrix = {
                f"{corr.columns[i]}_{corr.columns[j]}": round(float(corr.iloc[i, j]), 4)
                for i in range(len(corr))
                for j in range(i + 1, len(corr))
                if abs(corr.iloc[i, j]) > 0.5
            }

        return {
            "status": "success",
            "rows": len(df),
            "cols": len(df.columns),
            "numeric_columns": list(numeric_stats.keys()),
            "categorical_columns": list(categorical_stats.keys()),
            "numeric_stats": numeric_stats,
            "categorical_stats": categorical_stats,
            "correlations": corr_matrix,
        }

    except Exception as e:
        return {"status": "error", "message": str(e)}


# ─── ReportGenerator ────────────────────────────────────────────────────────

def gen_report(
    data_path: str,
    output_path: Optional[str] = None,
    title: str = "数据质量报告",
) -> Dict[str, Any]:
    """
    生成完整的 HTML 数据质量报告
    """
    try:
        import pandas as pd

        # 收集所有信息
        load_result = load_data(data_path)
        if load_result["status"] != "success":
            return load_result

        quality = quality_check(data_path)
        stats = calc_stats(data_path)

        # 生成 HTML 报告
        html = f"""<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="utf-8">
<title>{title}</title>
<style>
  body {{ font-family: 'Segoe UI', sans-serif; margin: 40px; background: #f5f5f5; }}
  .container {{ max-width: 1000px; margin: auto; background: white; padding: 30px; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); }}
  h1 {{ color: #333; border-bottom: 2px solid #4a90d9; padding-bottom: 10px; }}
  h2 {{ color: #4a90d9; margin-top: 30px; }}
  .score {{ font-size: 48px; font-weight: bold; text-align: center; color: {'#4caf50' if quality['quality_score'] >= 80 else '#ff9800' if quality['quality_score'] >= 60 else '#f44336'}; }}
  .score-label {{ text-align: center; color: #888; margin-bottom: 30px; }}
  table {{ width: 100%; border-collapse: collapse; margin-top: 10px; }}
  th, td {{ padding: 10px 14px; text-align: left; border-bottom: 1px solid #eee; }}
  th {{ background: #f8f9fa; color: #555; font-weight: 600; }}
  tr:hover {{ background: #f8f9fa; }}
  .badge {{ display: inline-block; padding: 2px 8px; border-radius: 12px; font-size: 12px; }}
  .badge-warning {{ background: #fff3cd; color: #856404; }}
  .badge-danger {{ background: #f8d7da; color: #721c24; }}
  .badge-success {{ background: #d4edda; color: #155724; }}
  .summary-grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 15px; margin: 20px 0; }}
  .summary-card {{ background: #f8f9fa; padding: 15px; border-radius: 6px; text-align: center; }}
  .summary-card .value {{ font-size: 24px; font-weight: bold; color: #4a90d9; }}
  .summary-card .label {{ font-size: 12px; color: #888; margin-top: 5px; }}
  .stat-row {{ display: grid; grid-template-columns: repeat(5, 1fr); gap: 8px; font-size: 13px; color: #666; text-align: center; }}
  .stat-row .header {{ font-weight: 600; color: #333; }}
</style>
</head>
<body>
<div class="container">
  <h1>{title}</h1>

  <h2>📊 概览</h2>
  <div class="summary-grid">
    <div class="summary-card"><div class="value">{load_result['rows']}</div><div class="label">总行数</div></div>
    <div class="summary-card"><div class="value">{load_result['cols']}</div><div class="label">总列数</div></div>
    <div class="summary-card"><div class="value">{quality['quality_score']}</div><div class="label">质量评分</div></div>
    <div class="summary-card"><div class="value">{quality['total_issues']}</div><div class="label">问题数量</div></div>
  </div>

  <h2>📋 列信息</h2>
  <table>
    <tr><th>列名</th><th>数据类型</th></tr>
    {''.join(f"<tr><td>{col}</td><td>{dtype}</td></tr>" for col, dtype in load_result['dtypes'].items())}
  </table>

  <h2>🔍 质量问题</h2>
  <p><strong>质量评分：</strong><span class="badge {'badge-success' if quality['quality_score'] >= 80 else 'badge-warning' if quality['quality_score'] >= 60 else 'badge-danger'}">{quality['quality_score']}/100</span></p>

  <p><strong>重复行：</strong> {quality['duplicate_rows']} 行</p>

  <h3>空值列（{len(quality['null_columns'])} 个）</h3>
  {"<table><tr><th>列名</th><th>空值数</th><th>空值比例</th></tr>" + ''.join(f"<tr><td>{i['column']}</td><td>{i['null_count']}</td><td>{i['null_pct']}%</td></tr>" for i in quality['null_columns']) + "</table>" if quality['null_columns'] else "<p>✅ 无空值</p>"}

  <h3>异常值列（{len(quality['outlier_columns'])} 个）</h3>
  {"<table><tr><th>列名</th><th>异常值数量</th><th>正常范围</th></tr>" + ''.join(f"<tr><td>{i['column']}</td><td>{i['count']} ({i['count_pct']}%)</td><td>{i['range']}</td></tr>" for i in quality['outlier_columns']) + "</table>" if quality['outlier_columns'] else "<p>✅ 无明显异常值</p>"}

  <h2>📈 数值列统计</h2>
  {''.join(f"<h3>{col}</h3><div class='stat-row'><span class='header'>min</span><span class='header'>max</span><span class='header'>mean</span><span class='header'>std</span><span class='header'>p50</span></div><div class='stat-row'>" + ''.join(f"<span>{s['min']:.2f}</span><span>{s['max']:.2f}</span><span>{s['mean']:.2f}</span><span>{s['std']:.2f}</span><span>{s['p50']:.2f}</span>" for col, s in stats['numeric_stats'].items()) + "</div>") if stats.get('numeric_stats') else "<p>无数值列</p>"}

  <h2>📁 分类列分布</h2>
  {''.join(f"<h3>{col}</h3><p>唯一值数量：{s['unique']}</p><table><tr><th>值</th><th>计数</th></tr>" + ''.join(f"<tr><td>{v}</td><td>{c}</td></tr>" for v, c in s['top_values'].items()) + "</table>" for col, s in stats.get('categorical_stats', {}).items()) if stats.get('categorical_stats') else "<p>无分类列</p>"}

  <p style="color:#888; margin-top:40px; text-align:center;">
    生成时间：{pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S')} | Codex-Local Data Cleaner
  </p>
</div>
</body>
</html>"""

        if output_path is None:
            out_dir = Path(os.environ.get("CODEX_DATA", "D:/codex-local/data"))
            out_dir.mkdir(parents=True, exist_ok=True)
            output_path = str(out_dir / "data_quality_report.html")

        Path(output_path).write_text(html, encoding="utf-8")

        return {
            "status": "success",
            "report_path": output_path,
            "quality_score": quality["quality_score"],
            "total_issues": quality["total_issues"],
        }

    except Exception as e:
        return {"status": "error", "message": str(e)}


# ─── Tool wrapper ────────────────────────────────────────────────────────────

def data_cleaner_tool(operation: str, **kwargs) -> Dict[str, Any]:
    """
    主入口，所有数据清洗操作都通过这个函数调用。
    """
    ops = {
        "load": lambda: load_data(kwargs.get("file_path", "")),
        "quality": lambda: quality_check(kwargs.get("file_path", "")),
        "clean": lambda: clean_data(
            file_path=kwargs.get("file_path", ""),
            output_path=kwargs.get("output_path"),
            remove_duplicates=kwargs.get("remove_duplicates", True),
            fill_numeric_nulls=kwargs.get("fill_numeric_nulls", 0.0),
            fill_string_nulls=kwargs.get("fill_string_nulls", ""),
            strip_whitespace=kwargs.get("strip_whitespace", True),
            rename_columns=kwargs.get("rename_columns", True),
        ),
        "stats": lambda: calc_stats(kwargs.get("file_path", "")),
        "report": lambda: gen_report(
            data_path=kwargs.get("file_path", ""),
            output_path=kwargs.get("output_path"),
            title=kwargs.get("title", "数据质量报告"),
        ),
    }

    if operation not in ops:
        return {"status": "error", "message": f"未知操作：{operation}，可用：{list(ops.keys())}"}

    try:
        return ops[operation]()
    except Exception as e:
        return {"status": "error", "message": str(e)}


if __name__ == "__main__":
    import sys
    file_path = sys.argv[2] if len(sys.argv) > 2 else ""
    op = sys.argv[1] if len(sys.argv) > 1 else "help"

    if op == "help":
        print("Usage: python data_cleaner.py <load|quality|clean|stats|report> <file_path>")
    else:
        result = data_cleaner_tool(op, file_path=file_path)
        print(json.dumps(result, ensure_ascii=False, indent=2))