English | [简体中文](README.md)
# doc2md Token Slim

Batch-convert documents (PDF, Word, Excel, PowerPoint, HTML, CSV, JSON, EPUB, ZIP, Outlook and more) to Markdown **with token slimming**, then let your AI assistant execute the full task on the slimmed output — end to end, without interruption.

> Conversion is the means. Completing your task is the goal.

## Why not just use markitdown?

The well-known `markitdown` skill/library does format conversion. This skill is a different thing, built for AI token efficiency:

| Dimension | markitdown | **doc2md-token-slim** |
|---|---|---|
| Goal | Format conversion | **Conversion + token reduction**, then executes your task |
| Scanned PDFs | Usually empty output | Per-page detection + high-DPI rendering + AI recognition (100% accuracy measured on Chinese documents) |
| Token optimization | None | Four-way slimming: line rejoin / header-footer removal / normalized dedup / thin index |
| Mixed PDFs (text + scanned pages) | Not handled | Page-by-page detection; text pages extracted, scanned pages recognized, results merged |
| Execution model | Conversion only | After conversion, **directly executes your task** in batches until done |
| Verification | None | Measured data with reproducible scripts |

## Measured token reduction

| Method | Effect (measured) |
|---|---|
| Markdown conversion (strips Office XML / PDF layout noise) | ~80% for Office files, ~73% for scanned PDFs |
| Normalized dedup (folds cross-page repeated template lines) | up to **98.7%** for templated PDFs |
| Header/footer removal (running titles, page numbers, confidentiality banners) | 61.6% for slide decks |
| Line rejoin (PDF one-line-per-sentence → full paragraphs) | depends on source |
| Thin index + on-demand reads | resident cost drops from full text to a few KB index |
| Scanned-page image recognition (image → text) | 2,898 → 783 tokens per page |

Deliberately **not** adopted: LLMLingua / Selective Context (token-level deletion breaks parameter names and doesn't guarantee semantic coherence), vector RAG (replaced by zero-dependency thin index + keyword location), prompt caching (a caller-side API optimization).

## Supported formats

pdf (text / scanned / mixed), docx, xlsx, xls, pptx, ppt (partial), html, csv, tsv, json, xml, epub, zip, txt, md, ipynb, msg (Outlook), images (jpg/png — metadata only, no OCR).

## Setup (once)

Requirements: **Python 3.10–3.13**. Do **not** use 3.14 — `magika` depends on `onnxruntime`, which has no 3.14 wheel and pip will hang in backtracking.

```bash
SD="<skill install directory>"                     # where SKILL.md lives
VENV="$HOME/.cache/doc2md-token-slim/venv"         # Windows: %LOCALAPPDATA%\doc2md-token-slim\venv
python3.13 -m venv "$VENV"                         # or python3.12 / python3.11

# Constraints required on Intel Macs (optional elsewhere)
cat > /tmp/doc2md-constraints.txt <<'EOF'
cryptography<=46.0.3
opencv-python-headless==4.11.0.86
EOF

# Install (uv is ~10x faster; or use the venv's pip)
uv pip install --python "$VENV/bin/python" -c /tmp/doc2md-constraints.txt \
  "markitdown[pdf,docx,xlsx,xls,pptx,outlook]" pypdfium2 pdfplumber tiktoken
```

Dependency roles: `markitdown` (conversion core), `pdfplumber` (per-page PDF detection), `pypdfium2` (high-DPI rendering of scanned pages), `tiktoken` (token estimation; degrades to character-count estimation if missing).

## Usage

```bash
PY="$VENV/bin/python"    # Windows: $VENV\Scripts\python.exe

# Convert non-PDF documents
"$PY" "$SD/scripts/mdconvert.py" /path/to/docs -r --ext docx xlsx pptx html csv json txt --json

# Convert PDFs (per-page text/scanned detection + rendering)
"$PY" "$SD/scripts/pdf2md.py" /path/to/docs -r --json

# Slim tokens (report only, no writes)
"$PY" "$SD/scripts/slim.py" /path/to/docs -r

# Slim + generate INDEX.md thin index
"$PY" "$SD/scripts/slim.py" /path/to/docs -r --index

# Overwrite in place with the slimmed result
"$PY" "$SD/scripts/slim.py" /path/to/docs -r --inplace

# Disable a specific optimization (e.g. for poetry or code documents)
"$PY" "$SD/scripts/slim.py" file.md --no-norm-dedup
```

Common flags: `-r` recursive; `--ext` restrict extensions; `-o DIR` output directory (relative structure preserved); `--stdout` print only; `--json` machine-readable; `--overwrite` allow overwriting (never overwrites by default); `--scale 4` higher rendering DPI; `--min-chars` adjust scanned-page threshold.

The first run downloads the magika model (~40 s, once only); subsequent runs take ~8 s.

### Safety guarantees

- **Never overwrites** existing files (unless `--overwrite`).
- Conservative slimming: **table rows, headings, lists and code blocks never participate** in merging or dedup — verified lossless on a 400-row table.
- Unrecognizable scanned text is marked `[unreadable]`, never guessed.
- Scanned pages are rendered locally and recognized by the AI directly — nothing is uploaded to external services.

## Typical prompts

- "Convert all docx, xlsx and pptx files under ~/Documents/2026-reports/ to Markdown, saved next to the originals."
- "This folder mixes scanned PDFs — detect each page, recognize the scanned ones, then summarize every maintenance record into a comparison table."
- "Convert this 300-page technical document to Markdown and slim it down, I need to keep token usage under control."

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `No module named markitdown` | Wrong interpreter | Resolve `$PY` per Setup; don't run with system Python |
| Install hangs for many minutes | Python 3.14 + onnxruntime has no wheel | Rebuild the venv with 3.10–3.13 |
| `could not compile cryptography` | cryptography ≥ 47 ships arm64 wheels only | Pin `cryptography<=46.0.3` (Intel Mac only) |
| No matching opencv version | opencv 5.0 supports `macosx_14_0_x86_64` only | Pin `opencv-python-headless==4.11.0.86` (Intel Mac + macOS 13) |
| Empty output / very low `chars` | Threshold misjudgment or encrypted file | Tune `--min-chars`; decrypt PDFs first |
| Content missing after slimming | An optimization misfired | Tables are never lost; for body text, retry with `--no-norm-dedup` |
| Poor scanned-page recognition | Low render DPI or blurry source | Use `--scale 4`; otherwise it's a source-quality limit |
| First run takes ~40 s | Downloading the magika model | Normal, first run only; ~8 s afterwards |

On Windows, if the magika model download fails on first run, check proxy settings and retry — the model is cached once downloaded.

## License

See [LICENSE](LICENSE).
