#!/usr/bin/env python3
"""
mdconvert.py - 本地 markitdown 封装：把各类文档转换为 Markdown，默认输出到源文件所在目录。

定位：供 AI 助手与命令行使用，支持单文件、多文件、目录递归，默认「原地」产出 .md。

用法示例：
    # 原地转换（默认）：在源文件同目录生成同名 .md
    mdconvert.py /path/to/file.docx

    # 批量：多个文件 + 目录递归
    mdconvert.py a.pdf b.docx ./docs -r

    # 只处理指定扩展名
    mdconvert.py ./docs -r --ext pdf docx

    # 指定输出目录（保持相对目录结构）
    mdconvert.py ./docs -r -o ./outputs

    # 直接打印到标准输出（不落盘）
    mdconvert.py /path/to/a.docx --stdout

    # 机器可读结果（JSON 清单，便于程序判断成功/失败）
    mdconvert.py ./docs -r --json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import traceback
from pathlib import Path

try:
    from markitdown import MarkItDown
except ImportError:  # pragma: no cover
    sys.stderr.write(
        "[mdconvert] 未找到 markitdown。请先按 SKILL.md「环境准备」章节创建虚拟环境并安装依赖，\n"
        "然后使用该虚拟环境的解释器运行本脚本，例如：\n"
        "  <venv>/bin/python "
        f"{os.path.abspath(__file__)} ...\n"
    )
    raise


SUPPORTED_HINT = (
    "常见支持类型：pdf, docx, doc, xlsx, xls, pptx, ppt, html, htm, csv, tsv, "
    "json, xml, epub, zip, txt, md, 图片(jpg/png 等，提取元数据), msg(Outlook), "
    "ipynb；音频转写/YouTube 字幕/Azure 文档智能需额外 extras"
)


def build_converter(use_plugins: bool = False) -> MarkItDown:
    """构造转换器，兼容不同版本构造签名。"""
    try:
        return MarkItDown(enable_plugins=use_plugins)
    except TypeError:
        try:
            return MarkItDown(enable_builtins=True, enable_plugins=use_plugins)
        except TypeError:
            return MarkItDown()


def iter_files(paths, recursive: bool, exts):
    """把输入路径展开为文件列表。"""
    exts = {e.lower().lstrip(".") for e in exts} if exts else None
    seen = set()
    for raw in paths:
        p = Path(raw).expanduser()
        if p.is_file():
            candidates = [p]
        elif p.is_dir():
            walk = p.rglob("*") if recursive else p.glob("*")
            candidates = [f for f in walk if f.is_file()]
        else:
            sys.stderr.write(f"[skip] 路径不存在：{p}\n")
            continue
        for f in candidates:
            if exts and f.suffix.lower().lstrip(".") not in exts:
                continue
            rp = f.resolve()
            if rp in seen:
                continue
            seen.add(rp)
            yield f


def resolve_destination(src: Path, out_root: Path | None) -> tuple[Path, Path]:
    """确定输出 .md 路径。

    返回 (首选路径, 备用路径)：
    - 原地模式：首选 `同名.md`，备用 `完整文件名.md`（如 report.docx.md）
    - 指定目录模式：在输出目录内保持源相对结构，命名规则相同
    """
    if out_root is None:
        base = src
    else:
        try:
            rel = src.resolve().relative_to(Path.cwd())
        except ValueError:
            rel = Path(src.name)
        base = out_root / rel
    return base.with_suffix(".md"), base.with_name(base.name + ".md")


def unique_path(dst: Path, alt: Path, overwrite: bool) -> Path:
    """避免覆盖：首选路径已存在时依次尝试备用路径、序号后缀。"""
    for candidate in (dst, alt):
        if not candidate.exists() or overwrite:
            return candidate
    stem, suffix, n = alt.stem, alt.suffix, 1
    while True:
        candidate = alt.with_name(f"{stem}_{n}{suffix}")
        if not candidate.exists() or overwrite:
            return candidate
        n += 1


def convert_one(conv: MarkItDown, src: Path) -> str:
    result = conv.convert(str(src))
    return result.markdown or ""


def main() -> int:
    ap = argparse.ArgumentParser(
        description="使用本地 markitdown 将文档转换为 Markdown（默认原地输出）",
        epilog=SUPPORTED_HINT,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("paths", nargs="+", help="输入文件或目录（可多个）")
    ap.add_argument(
        "-o", "--out-dir", default=None,
        help="输出目录；省略时在源文件同目录生成同名 .md（原地模式）",
    )
    ap.add_argument("-r", "--recursive", action="store_true", help="递归处理子目录")
    ap.add_argument("--ext", nargs="*", default=None, help="只处理这些扩展名")
    ap.add_argument("--stdout", action="store_true", help="将结果打印到标准输出，不落盘")
    ap.add_argument("--overwrite", action="store_true", help="允许覆盖已存在的 .md")
    ap.add_argument("--plugins", action="store_true", help="启用第三方 markitdown 插件")
    ap.add_argument("--json", action="store_true", help="输出 JSON 结果清单")
    args = ap.parse_args()

    conv = build_converter(use_plugins=args.plugins)
    out_root = Path(args.out_dir).expanduser().resolve() if args.out_dir else None
    if out_root:
        out_root.mkdir(parents=True, exist_ok=True)

    records = []
    for src in iter_files(args.paths, args.recursive, args.ext):
        rec = {"source": str(src.resolve()), "status": "ok", "output": "", "chars": 0, "error": ""}
        try:
            text = convert_one(conv, src)
            rec["chars"] = len(text)
            if args.stdout:
                sys.stdout.write(f"----- BEGIN {src} -----\n{text}\n----- END {src} -----\n\n")
            if out_root or not args.stdout:
                dst, alt = resolve_destination(src, out_root)
                if out_root:
                    dst.parent.mkdir(parents=True, exist_ok=True)
                dst = unique_path(dst, alt, args.overwrite)
                try:
                    dst.write_text(text, encoding="utf-8")
                except OSError as e:
                    raise OSError(
                        f"无法写入 {dst}（{e}）。原目录可能无写权限，"
                        "请改用 -o 指定一个可写目录。"
                    ) from e
                rec["output"] = str(dst)
        except Exception as exc:  # noqa: BLE001
            rec["status"] = "error"
            rec["error"] = f"{type(exc).__name__}: {exc}"
            if not args.json:
                sys.stderr.write(f"[error] {src}: {rec['error']}\n")
        records.append(rec)

    if args.json:
        print(json.dumps(records, ensure_ascii=False, indent=2))

    failed = [r for r in records if r["status"] != "ok"]
    if records and not args.json:
        sys.stderr.write(
            f"[summary] 共 {len(records)} 个文件：成功 {len(records) - len(failed)}，失败 {len(failed)}\n"
        )
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
