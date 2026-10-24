#!/usr/bin/env python3
"""
pdf2md.py - PDF 转 Markdown 的判别与预处理脚本（支持扫描件 / 混合页）。

工作方式（人机分工）：
  本脚本负责机械部分：
    1. 逐页判别：文本型页 vs 扫描型页
    2. 文本型页 → 直接用 markitdown 抽取文字
    3. 扫描型页 → 用 pypdfium2 渲染为高清 PNG，并写入待识别清单 manifest.json
  随后由 AI 助手读取 manifest 中的 PNG，转写为 Markdown，最终合并产出 .md。

用法：
    # 单文件（原地）
    pdf2md.py /path/to/file.pdf --json

    # 目录递归
    pdf2md.py /path/to/docs -r --json

判别阈值说明：
    单页可提取字符数 < --min-chars（默认 20）即判定为扫描页。
    20 是经验值：真实文本页即便只有标题也远超此值；低于此值通常意味着
    页面是整幅图像（扫描/拍照），文字以像素形式存在而非文本层。

退出码：0 = 全部处理完成（含生成待识别清单）；1 = 存在失败文件。
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import traceback
from pathlib import Path

MIN_CHARS_DEFAULT = 20
RENDER_SCALE_DEFAULT = 3  # 150dpi × 3 ≈ 300dpi，识别质量与体积的平衡点


def log(msg: str) -> None:
    sys.stderr.write(f"[pdf2md] {msg}\n")


def analyze_page(page) -> tuple[str, int]:
    """判别单页类型，返回 (类型, 字符数)。类型为 'text' 或 'scanned'。"""
    try:
        import pdfplumber
        with pdfplumber.open_page(page) as p:  # type: ignore[attr-defined]
            n = len(p.chars)
    except Exception:
        n = -1
    return n


def classify_pdf(pdf_path: Path, min_chars: int) -> list[dict]:
    """逐页判别。返回每页信息：[{page, chars, type}]"""
    import pdfplumber

    pages: list[dict] = []
    with pdfplumber.open(str(pdf_path)) as pdf:
        for idx, page in enumerate(pdf.pages, start=1):
            try:
                n = len(page.chars)
            except Exception:
                n = -1
            kind = "text" if n >= min_chars else "scanned"
            pages.append({"page": idx, "chars": n, "type": kind})
    return pages


def render_pages(pdf_path: Path, out_dir: Path, pages: list[int], scale: int) -> list[str]:
    """把指定页渲染为 PNG，返回图片路径列表（顺序与 pages 一致）。"""
    import pypdfium2 as pdfium

    pdf = pdfium.PdfDocument(str(pdf_path))
    images: list[str] = []
    out_dir.mkdir(parents=True, exist_ok=True)
    for pno in pages:
        page = pdf[pno - 1]
        img = page.render(scale=scale).to_pil()
        dst = out_dir / f"page_{pno:04d}.png"
        img.save(dst, "PNG")
        images.append(str(dst))
    return images


def extract_text_pages(pdf_path: Path) -> str:
    """对纯文本型 PDF，直接用 markitdown 抽取全文。"""
    from markitdown import MarkItDown

    md = MarkItDown(enable_plugins=False)
    result = md.convert(str(pdf_path))
    return result.markdown or ""


def unique_md_path(src: Path) -> Path:
    """确定 .md 输出路径：同名.md → 完整文件名.md → 序号。永不覆盖。"""
    primary = src.with_suffix(".md")
    alt = src.with_name(src.name + ".md")
    for cand in (primary, alt):
        if not cand.exists():
            return cand
    stem, suffix, n = alt.stem, alt.suffix, 1
    while True:
        cand = alt.with_name(f"{stem}_{n}{suffix}")
        if not cand.exists():
            return cand
        n += 1


def process_pdf(pdf_path: Path, min_chars: int, scale: int, keep_pages: bool) -> dict:
    rec: dict = {
        "source": str(pdf_path.resolve()),
        "status": "ok",
        "pdf_type": "",
        "pages": 0,
        "text_pages": 0,
        "scanned_pages": 0,
        "md_path": "",
        "pages_dir": "",
        "images": [],
        "manifest": "",
        "error": "",
    }
    try:
        info = classify_pdf(pdf_path, min_chars)
        rec["pages"] = len(info)
        rec["text_pages"] = sum(1 for p in info if p["type"] == "text")
        rec["scanned_pages"] = sum(1 for p in info if p["type"] == "scanned")

        # 情况一：纯文本型 → 直接 markitdown 转换（快速路径）
        if rec["scanned_pages"] == 0:
            rec["pdf_type"] = "text"
            text = extract_text_pages(pdf_path)
            dst = unique_md_path(pdf_path)
            dst.write_text(text, encoding="utf-8")
            rec["md_path"] = str(dst)
            rec["chars"] = len(text)
            log(f"{pdf_path.name}: 纯文本型（{rec['pages']} 页），已直接转换 → {dst.name}")
            return rec

        # 情况二：含扫描页（纯扫描或混合）
        rec["pdf_type"] = "scanned" if rec["text_pages"] == 0 else "mixed"
        pages_dir = pdf_path.parent / (pdf_path.stem + ".pages")
        scan_page_nos = [p["page"] for p in info if p["type"] == "scanned"]
        images = render_pages(pdf_path, pages_dir, scan_page_nos, scale)
        rec["pages_dir"] = str(pages_dir)
        rec["images"] = images

        # 文本页先抽出来，减少 AI 需要识别的页数
        rec["text_extract"] = extract_text_pages(pdf_path) if rec["text_pages"] else ""

        manifest = pages_dir / "manifest.json"
        manifest.write_text(
            json.dumps(
                {
                    "pdf": str(pdf_path.resolve()),
                    "pdf_type": rec["pdf_type"],
                    "total_pages": rec["pages"],
                    "text_pages": rec["text_pages"],
                    "scanned_pages": rec["scanned_pages"],
                    "render_scale": scale,
                    "page_detail": info,
                    "images": images,
                    "instruction": (
                        "由 AI 助手依次读取 images 中的 PNG，将图片内容准确转写为 Markdown"
                        "（保留标题层级、表格、列表、数字与单位），"
                        "最后与 text_extract 合并，写入 pdf 同目录的 .md 文件。"
                    ),
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        rec["manifest"] = str(manifest)
        log(
            f"{pdf_path.name}: {rec['pdf_type']}（共 {rec['pages']} 页，"
            f"扫描 {rec['scanned_pages']} 页 / 文本 {rec['text_pages']} 页），"
            f"已渲染 {len(images)} 张图片 → {pages_dir.name}/，等待识别"
        )
        return rec
    except Exception as exc:  # noqa: BLE001
        rec["status"] = "error"
        rec["error"] = f"{type(exc).__name__}: {exc}"
        sys.stderr.write(f"[error] {pdf_path}: {rec['error']}\n")
        sys.stderr.write(traceback.format_exc(limit=2))
        return rec


def iter_pdfs(paths, recursive: bool):
    seen = set()
    for raw in paths:
        p = Path(raw).expanduser()
        if p.is_file():
            cands = [p] if p.suffix.lower() == ".pdf" else []
        elif p.is_dir():
            walk = p.rglob("*.pdf") if recursive else p.glob("*.pdf")
            cands = [f for f in walk if f.is_file()]
        else:
            log(f"路径不存在：{p}")
            continue
        for f in cands:
            rp = f.resolve()
            if rp not in seen:
                seen.add(rp)
                yield f


def main() -> int:
    ap = argparse.ArgumentParser(
        description="PDF 判别与预处理：文本页直接转换，扫描页渲染为图片供 AI 识别",
    )
    ap.add_argument("paths", nargs="+", help="PDF 文件或目录")
    ap.add_argument("-r", "--recursive", action="store_true", help="递归子目录")
    ap.add_argument(
        "--min-chars", type=int, default=MIN_CHARS_DEFAULT,
        help=f"单页字符数低于此值判定为扫描页（默认 {MIN_CHARS_DEFAULT}）",
    )
    ap.add_argument(
        "--scale", type=int, default=RENDER_SCALE_DEFAULT,
        help=f"渲染倍率，越大越清晰（默认 {RENDER_SCALE_DEFAULT} ≈ 300dpi）",
    )
    ap.add_argument("--json", action="store_true", help="输出 JSON 结果")
    args = ap.parse_args()

    records = [process_pdf(p, args.min_chars, args.scale, False) for p in iter_pdfs(args.paths, args.recursive)]
    if args.json:
        print(json.dumps(records, ensure_ascii=False, indent=2))

    failed = [r for r in records if r["status"] != "ok"]
    if records:
        log(f"共 {len(records)} 个 PDF：成功 {len(records) - len(failed)}，失败 {len(failed)}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
