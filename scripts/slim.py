#!/usr/bin/env python3
"""
slim.py - Markdown token 瘦身：在 markitdown 转换之后执行，进一步压缩提交给 AI 的文本。

三项优化（均可单独开关）：
  1. reflow   断行重连：把 PDF/扫描抽取产生的"一行一句"合并为完整段落
  2. header   页眉页脚移除：识别并删除跨页重复的短行（标题栏、页码、保密声明）
  3. dedup    连续重复行折叠：折叠连续重复 3 次以上的相同行（排除表格与标题）
  4. index    生成 INDEX.md 薄索引：文件名 + 标题结构 + 字数，供 AI 按需取全文

设计原则：保守优先。宁可少压，不可误删——所有策略都只作用于
"明确属于版式噪音"的内容，不触碰正文语义。

用法：
    slim.py /path/to/a.md                     # 单文件优化（原地覆盖优化版）
    slim.py /path/to/docs -r                  # 目录递归 + 生成索引
    slim.py /path/to/docs -r --index          # 仅生成索引
    slim.py /path/to/a.md --json              # 输出优化前后 token 对比
    slim.py /path/to/a.md --no-dedup          # 关闭某项优化
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

try:
    import tiktoken
    _ENC = tiktoken.get_encoding("cl100k_base")
except Exception:  # pragma: no cover
    _ENC = None

SENT_END = tuple("。！？；.!?;:")
STRUCT_PREFIX = ("#", "-", "*", ">", "|", "```", "    ", "\t", "<!--")


def tok(text: str) -> int:
    if _ENC is None:
        return len(text)
    return len(_ENC.encode(text, disallowed_special=()))


def is_structural(line: str) -> bool:
    """是否是结构性行（标题/列表/表格/代码/引用），这类行不参与合并与去重。"""
    s = line.strip()
    if not s:
        return True
    if s.startswith(STRUCT_PREFIX):
        return True
    # 列表项要求「数字/序号 + 标点 + 空白」；"1.1 正文" 是编号前缀而非列表
    if re.match(r"^\d+[.、)]\s", s) is not None:
        return True
    return False


def normalize_line(s: str) -> str:
    """去掉行首的页码/编号前缀，用于识别跨页重复的模板句。"""
    s = re.sub(r"^\d+(\.\d+)*[.、)]?\s+", "", s)
    return s.strip()


def reflow_lines(lines: list[str]) -> tuple[list[str], int]:
    """断行重连：把段内硬换行合并为完整句子。返回 (新行, 合并次数)。"""
    out: list[str] = []
    merged = 0
    buf = ""
    for raw in lines:
        line = raw.rstrip()
        s = line.strip()
        if not s:
            if buf:
                out.append(buf)
                buf = ""
            out.append("")
            continue
        if is_structural(s):
            if buf:
                out.append(buf)
                buf = ""
            out.append(line)
            continue
        if buf:
            # 上一行未以句末标点结束 → 判定为跨行断句，合并
            if not buf.rstrip().endswith(SENT_END):
                buf = buf.rstrip() + s
                merged += 1
                continue
            out.append(buf)
            buf = s
        else:
            buf = s
    if buf:
        out.append(buf)
    return out, merged


def strip_running_headers(lines: list[str], min_repeat: int = 3, max_len: int = 40) -> tuple[list[str], int]:
    """移除跨页重复的页眉页脚：短行且全文出现 ≥ min_repeat 次。"""
    candidates = Counter()
    for line in lines:
        s = line.strip()
        if s and len(s) <= max_len and not is_structural(s):
            candidates[s] += 1
    noise = {t for t, c in candidates.items() if c >= min_repeat}
    if not noise:
        return lines, 0
    out, removed = [], 0
    for line in lines:
        if line.strip() in noise:
            removed += 1
            continue
        out.append(line)
    return out, removed


def collapse_repeats(lines: list[str], min_run: int = 3) -> tuple[list[str], int]:
    """折叠连续重复行：相同行连续出现 ≥ min_run 次时只保留一个。"""
    out: list[str] = []
    collapsed = 0
    run = 0
    prev = None
    for line in lines:
        s = line.strip()
        if s and not is_structural(s) and s == prev:
            run += 1
            if run >= min_run:
                collapsed += 1
                continue
        else:
            run = 1
            prev = s
        out.append(line)
    return out, collapsed


def dedup_normalized(lines: list[str], min_len: int = 15) -> tuple[list[str], int]:
    """归一化去重：去掉行首编号/页码前缀后，折叠全文重复的模板句。

    PDF 逐页抽取常产生「每页重复相同句式、仅行号不同」的噪音，
    连续去重无法捕获，需按归一化内容判断。min_len 防止短行误删。
    """
    seen: set[str] = set()
    out: list[str] = []
    removed = 0
    for line in lines:
        s = line.strip()
        if not s or is_structural(s):
            out.append(line)
            continue
        norm = normalize_line(s)
        if len(norm) >= min_len and norm in seen:
            removed += 1
            continue
        seen.add(norm)
        out.append(line)
    return out, removed


def build_index_entry(path: Path) -> dict:
    """从 md 提取索引信息：标题结构、字数、表格数。"""
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    h1 = next((l.lstrip("# ").strip() for l in lines if l.startswith("# ")), path.stem)
    heads = [l.strip() for l in lines if re.match(r"^#{1,3} ", l)]
    tables = sum(1 for l in lines if l.strip().startswith("|"))
    chars = len(re.sub(r"\s", "", text))
    return {
        "file": path.name,
        "title": h1,
        "headings": heads[:12],
        "heading_count": len(heads),
        "table_rows": tables,
        "chars": chars,
        "tokens_est": tok(text),
    }


def slim_text(text: str, do_reflow=True, do_header=True, do_dedup=True,
              do_norm_dedup=True) -> tuple[str, dict]:
    lines = text.splitlines()
    stats = {"lines_in": len(lines), "reflow": 0, "header": 0, "dedup": 0, "norm_dedup": 0}
    if do_reflow:
        lines, stats["reflow"] = reflow_lines(lines)
    if do_header:
        lines, stats["header"] = strip_running_headers(lines)
    if do_dedup:
        lines, stats["dedup"] = collapse_repeats(lines)
    if do_norm_dedup:
        lines, stats["norm_dedup"] = dedup_normalized(lines)
    # 压缩连续空行
    cleaned: list[str] = []
    blank = 0
    for l in lines:
        if not l.strip():
            blank += 1
            if blank > 1:
                continue
        else:
            blank = 0
        cleaned.append(l)
    stats["lines_out"] = len(cleaned)
    return "\n".join(cleaned).strip() + "\n", stats


def iter_mds(paths, recursive: bool):
    seen = set()
    for raw in paths:
        p = Path(raw).expanduser()
        if p.is_file():
            cands = [p] if p.suffix.lower() == ".md" else []
        elif p.is_dir():
            walk = p.rglob("*.md") if recursive else p.glob("*.md")
            cands = [f for f in walk if f.is_file() and f.name != "INDEX.md"]
        else:
            sys.stderr.write(f"[skip] 路径不存在：{p}\n")
            continue
        for f in cands:
            rp = f.resolve()
            if rp not in seen:
                seen.add(rp)
                yield f


def main() -> int:
    ap = argparse.ArgumentParser(description="Markdown token 瘦身（断行重连/页眉页脚/重复折叠/索引生成）")
    ap.add_argument("paths", nargs="+", help="md 文件或目录")
    ap.add_argument("-r", "--recursive", action="store_true")
    ap.add_argument("--no-reflow", action="store_true", help="关闭断行重连")
    ap.add_argument("--no-header", action="store_true", help="关闭页眉页脚移除")
    ap.add_argument("--no-dedup", action="store_true", help="关闭重复行折叠")
    ap.add_argument("--no-norm-dedup", action="store_true", help="关闭归一化去重（跨页模板句）")
    ap.add_argument("--index", action="store_true", help="生成 INDEX.md 薄索引（需目录输入）")
    ap.add_argument("--inplace", action="store_true", help="原地覆盖优化结果（默认只报告，不覆盖）")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    do_reflow = not args.no_reflow
    do_header = not args.no_header
    do_dedup = not args.no_dedup
    do_norm_dedup = not args.no_norm_dedup

    records = []
    for md in iter_mds(args.paths, args.recursive):
        original = md.read_text(encoding="utf-8", errors="replace")
        slimmed, stats = slim_text(original, do_reflow, do_header, do_dedup, do_norm_dedup)
        before, after = tok(original), tok(slimmed)
        rec = {
            "file": str(md.resolve()),
            "tokens_before": before,
            "tokens_after": after,
            "saved": before - after,
            "saving_pct": round((1 - after / before) * 100, 1) if before else 0.0,
            **stats,
        }
        if args.inplace and after < before:
            md.write_text(slimmed, encoding="utf-8")
            rec["written"] = True
        records.append(rec)

        # 索引条目
        if args.index:
            pass

    # 生成薄索引
    index_path = None
    if args.index:
        for raw in args.paths:
            p = Path(raw).expanduser()
            if p.is_dir():
                entries = [build_index_entry(f) for f in iter_mds([p], args.recursive)]
                index_path = p / "INDEX.md"
                lines = [
                    "# 文档索引（薄索引）",
                    "",
                    "> 用法：先读本索引定位相关文档，再按需读取对应 .md 全文。",
                    "> 常驻成本仅为索引本身，避免一次性载入全部文档。",
                    "",
                    "| 文件 | 标题 | 标题数 | 表格行 | 字符 | 约 tokens |",
                    "| --- | --- | --- | --- | --- | --- |",
                ]
                for e in sorted(entries, key=lambda x: x["file"]):
                    lines.append(
                        f"| [{e['file']}]({e['file']}) | {e['title']} | {e['heading_count']} "
                        f"| {e['table_rows']} | {e['chars']:,} | {e['tokens_est']:,} |"
                    )
                total_tok = sum(e["tokens_est"] for e in entries)
                lines += [
                    "",
                    f"**共 {len(entries)} 个文档，全文合计约 {total_tok:,} tokens；"
                    f"本索引约 {tok(chr(10).join(lines)):,} tokens。**",
                ]
                index_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
                break

    if args.json:
        print(json.dumps({
            "records": records,
            "index": str(index_path) if index_path else "",
            "total_before": sum(r["tokens_before"] for r in records),
            "total_after": sum(r["tokens_after"] for r in records),
        }, ensure_ascii=False, indent=2))
    else:
        print(f"{'文件':<28}{'优化前':>10}{'优化后':>10}{'降幅':>9}  明细")
        print("-" * 78)
        for r in records:
            detail = f"重连{r['reflow']} 页眉{r['header']} 折叠{r['dedup']}"
            print(f"{Path(r['file']).name:<28}{r['tokens_before']:>10,}{r['tokens_after']:>10,}"
                  f"{r['saving_pct']:>8.1f}%  {detail}")
        print("-" * 78)
        tb = sum(r["tokens_before"] for r in records)
        ta = sum(r["tokens_after"] for r in records)
        if tb:
            print(f"{'合计':<28}{tb:>10,}{ta:>10,}{(1-ta/tb)*100:>8.1f}%")
        if index_path:
            print(f"\n索引已生成：{index_path}")
        if not args.inplace:
            print("\n（未写入；加 --inplace 原地覆盖优化结果）")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
