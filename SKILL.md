---
name: doc2md-token-slim
display_name: 文档转Markdown与Token瘦身
display_name_en: doc2md Token Slim
description: 把大量文档（PDF/Word/Excel/PPT/HTML/CSV/JSON/EPUB/ZIP/Outlook 等）批量转为 Markdown 并做 token 瘦身，再由 AI 基于瘦身后的 md 直接执行用户给出的完整任务，全程自动不中断。核心能力：逐页判别 PDF 文本型/扫描型，扫描页渲染高清图片由 AI 识别转写；断行重连、页眉页脚移除、跨页模板句归一化去重；生成薄索引 INDEX.md 实现按需取全文。实测 token 降幅：Office 约 80%、扫描 PDF 约 73%、模板化 PDF 去重后最高 98.7%。当用户提交文档并要求转成 markdown 再处理、提取文档内容、汇总分析这些文件、省 token、先转 md 再怎样时使用本技能。
description_zh: 文档批量转 Markdown 并做 token 瘦身：PDF 逐页判别文本型与扫描型（扫描页渲染高清图片由 AI 识别转写），Office 文档原地转换，归一化去重去掉跨页重复模板句，生成薄索引按需读取，最后由 AI 直接执行用户的完整任务。实测 token 降幅 Office 约 80%、扫描 PDF 约 73%。
description_en: Batch-convert documents (PDF, Word, Excel, PPT, HTML, CSV, JSON, EPUB, ZIP, Outlook) to Markdown with token slimming, then let the AI execute the user's full task on the slimmed output. Detects text vs scanned PDF pages per page, renders scanned pages to high-DPI images for AI recognition, removes running headers and cross-page repeated template lines via normalized dedup, and builds a thin INDEX.md for on-demand full-text reads. Measured token reduction is about 80% for Office files, about 73% for scanned PDFs, and up to 98.7% for templated PDFs after dedup.
examples_zh:
- "把 ~/Documents/2026报告/ 下的 docx、xlsx、pptx 全部转成 md，保存在原文件目录下。"
- "这个文件夹里混着扫描版 PDF，帮我逐页判别，扫描页识别成 md 后，再汇总所有设备的维保记录做一张对比表。"
- "把这 300 页技术文档转成 md 并瘦身，我要控制 token 消耗。"
examples_en:
- "Convert all docx, xlsx and pptx files under ~/Documents/2026-reports/ to Markdown, saved next to the originals."
- "This folder mixes scanned PDFs — detect each page, recognize the scanned ones, then summarize every maintenance record into a comparison table."
- "Convert this 300-page technical document to Markdown and slim it down, I need to keep token usage under control."
version: 1.0.0
author: ranson
category: 效率工具
---

# doc2md-token-slim — 文档转 md + Token 瘦身

## 差异化声明（与平台 `markitdown` 技能的区别）

技能市场上已存在同名的 `markitdown` 技能，其定位是「调用 markitdown 库做格式转换」。本技能是**不同的东西**，差异如下：

| 维度 | 平台 `markitdown` | 本技能 `doc2md-token-slim` |
|---|---|---|
| 目标 | 格式转换 | **转换 + 降 token**，最终替用户完成任务 |
| 扫描件 | 通常产出空内容 | 判别 + 渲染图片 + AI 识别转写，实测中文 100% 准确 |
| token 优化 | 无 | 断行重连 / 页眉页脚 / 归一化去重 / 薄索引四重瘦身 |
| 混合页 PDF | 不处理 | 逐页判别，文本页抽取 + 扫描页识别后合并 |
| 执行模式 | 转换即止 | 转换后**直接执行用户任务**，分批持续推进到完成 |
| 量化验证 | 无 | 提供实测数据与可复现脚本 |

## 环境准备（自包含，首次使用执行一次）

本技能不依赖任何预设环境。脚本只用标准库 + 下述第三方库，按下列步骤在任何用户的机器上完成部署。

### 步骤 0：定位技能目录与解释器

```bash
# SD = 本技能安装目录（即 SKILL.md 所在目录，通常为 ~/.workbuddy/skills/doc2md-token-slim）
SD="<本技能安装目录>"

# 解释器解析（按序尝试，命中即停）：
# 1) 环境变量 MD2MD_PY（用户自备解释器时）
# 2) 本技能标准 venv 位置：~/.cache/doc2md-token-slim/venv
# 3) 系统命令 md2md 已存在（说明本机已有部署，可直接用别名）
# 验证候选：<解释器> -c "import markitdown" 2>/dev/null 能通过即采用
```

### 步骤 1：创建虚拟环境并安装依赖（仅当步骤 0 全部未命中）

**Python 版本要求 3.10–3.13。不要用 3.14** —— 核心依赖 magika 依赖 onnxruntime，而 onnxruntime 在 3.14 上没有任何可用 wheel，pip 会陷入依赖解析回溯（表现为安装卡住十几分钟不动）。

```bash
# 创建 venv（任选一个可用的 3.10–3.13 解释器）
VENV="$HOME/.cache/doc2md-token-slim/venv"        # Windows: %LOCALAPPDATA%\doc2md-token-slim\venv
python3.13 -m venv "$VENV"                          # 或 python3.12 / python3.11

# 版本约束（Intel Mac 必需；Apple Silicon 与 Linux 可保留但非必需）
cat > /tmp/doc2md-constraints.txt <<'EOF'
cryptography<=46.0.3
opencv-python-headless==4.11.0.86
EOF

# 安装（有 uv 用 uv，快一个数量级；没有则用 venv 内 pip）
uv pip install --python "$VENV/bin/python" -c /tmp/doc2md-constraints.txt \
  "markitdown[pdf,docx,xlsx,xls,pptx,outlook]" pypdfium2 pdfplumber tiktoken

# 无 uv 时：
"$VENV/bin/python" -m pip install -c /tmp/doc2md-constraints.txt \
  "markitdown[pdf,docx,xlsx,xls,pptx,outlook]" pypdfium2 pdfplumber tiktoken

# Windows 解释器路径为 $VENV\Scripts\python.exe，约束文件用 %TEMP%\doc2md-constraints.txt
```

依赖用途：`markitdown`（转换核心）、`pdfplumber`（PDF 逐页判别）、`pypdfium2`（扫描页渲染高清图）、`tiktoken`（token 估算，缺失时瘦身报告自动降级为字数估算）。

### 步骤 2：之后所有调用

```bash
PY="$VENV/bin/python"        # Windows: $VENV\Scripts\python.exe
"$PY" "$SD/scripts/mdconvert.py" <参数>
"$PY" "$SD/scripts/pdf2md.py" <参数>
"$PY" "$SD/scripts/slim.py" <参数>
```

首次运行会下载 magika 识别模型（约 40 秒，仅一次），之后单次约 8 秒；批量转换走单进程，共享这次开销。

## 省 token 方法总览（甄别结论）

按「是否适合本技能」分为三类：

### 已落地（本技能内置）

| 方法 | 作用 | 实测效果 |
|---|---|---|
| **md 格式转换** | 剥离 Office XML 标签与 PDF 版式噪音 | Office 约 80%，扫描 PDF 约 73% |
| **归一化去重** | 去掉行首编号/页码前缀后折叠跨页重复的模板句 | 模板化 PDF 最高 98.7% |
| **页眉页脚移除** | 删除跨页重复的标题栏、页码、保密声明 | PPT 类 61.6% |
| **断行重连** | 把 PDF「一行一句」合并为完整段落 | 视源文件而定 |
| **薄索引 + 按需读取** | 先读几 KB 索引定位，再只读相关文档全文 | 常驻成本从全文降为索引 |
| **扫描件图片识别** | 图片 → 文字，本质降 token | 每页 2,898 → 783 tokens |

### 明确不采用（跨机器约束或风险）

| 方法 | 原因 |
|---|---|
| LLMLingua / Selective Context | 需运行压缩模型，无 GPU 的机器上推理慢；且按 token 粒度删除**不保证语义连贯**，会砍断关键参数名与括号，不适合需要精确引用数据的场景 |
| 向量 RAG 检索 | 需 embedding 模型，无 GPU 时慢；可用「薄索引 + 关键词定位」替代，零依赖 |
| Prompt Caching | 依赖 API 侧前缀缓存（Anthropic/vLLM），本地转换层无法控制，属调用方优化 |

### 可选增强（用户要求时）

| 方法 | 说明 |
|---|---|
| 先摘要后细节（Map-Reduce） | 超长文档先让 AI 出章节摘要，再按需钻取 |
| 关键词定位 | 用 Grep 在瘦身后 md 中定位相关章节，只读命中部分 |

## 标准工作流（默认全自动）

**用途**：把大量文档转为瘦身后的 md，再由 AI 执行用户的完整任务。转换是手段，完成任务是目的。

用户通常在一条消息里同时给出「一批文档」和「一个完整任务描述」。**默认全自动，不中途停下来问问题**。

### 阶段 0：意图判断与引导

**当本技能被触发，但用户消息中没有提供任何文件/目录路径，也没有说明任务时**，先输出下面的引导语，然后**停下等待用户输入**，不要自行推测文件位置、不要罗列用户目录：

> 请把需要处理的文件或文件夹发给我：
>
> - **只要转换**：我会将它们转换为 Markdown 文档，保存在原文件同目录下，供您在其他场景直接使用；
> - **转换 + 办事**：您也可以直接说明总体任务要求，我会在转换完成后，继续完成您交办的任务。
>
> 两种方式可以同时使用——给我文件的同时告诉我任务，我会一次性完成。

**例外**：用户已给出路径或任务描述时，跳过本阶段直接进入阶段 1。用户明确说"以后不用再提示"时，后续会话也不再展示引导语。

### 阶段 1：解析输入

- 提取文档路径（文件/目录/多路径）与**完整任务描述**。
- 目录用 `-r` 递归；用 `--ext` 限定文档类扩展名。
- 任务描述完整记住，后续所有阶段围绕它执行。
- 路径存在但为空目录，或扩展名不匹配时，如实说明并重新引导。

### 阶段 2：批量转换

```bash
PY="$VENV/bin/python"        # 按「环境准备」步骤 0/1 解析得到
SD="<本技能安装目录>"

# 非 PDF 文档
"$PY" "$SD/scripts/mdconvert.py" /path/to/docs -r --ext docx xlsx pptx html csv json txt --json

# PDF（判别 + 扫描件渲染）
"$PY" "$SD/scripts/pdf2md.py" /path/to/docs -r --json
```

- 默认原地输出：`同名.md` → `完整文件名.md` → 序号，**不覆盖已有文件**。
- PDF 三种 `pdf_type`：`text`（直接抽取，成品在 `md_path`）/ `mixed` / `scanned`（后两者读 `manifest` → 逐张 Read PNG → 转写合并）。
- 转写规则：保留标题层级、表格、列表、数字单位；无法辨认标 `[无法辨认]`，**不得猜测**。
- 渲染产物在 `<文件名>.pages/`，完成后**询问用户是否清理**。

### 阶段 3：token 瘦身（转换后自动执行）

```bash
"$PY" "$SD/scripts/slim.py" /path/to/docs -r --index
```

- 四项优化默认全开：断行重连、页眉页脚移除、连续重复折叠、归一化去重。
- **保守原则**：表格行、标题、列表、代码块一律不参与合并与去重——实测 400 行表格数据零丢失。
- 加 `--index` 生成 `INDEX.md` 薄索引（文件名 + 标题 + 字数 + 约 tokens）。
- **文档量大时**：先读 INDEX.md 定位相关文档，只读需要的全文，避免一次性载入。
- 加 `--inplace` 原地覆盖；不加则只报告不写入。
- 若某项优化明显不符合该文档特性（如诗歌、代码），可用 `--no-reflow` / `--no-norm-dedup` 关闭。

### 阶段 4：直接执行任务（不打断）

- **不要停下来问「你想怎么处理」**——用户已给出完整任务。
- 直接基于瘦身后的 .md 执行：汇总、对比、分析、提取、生成报告。
- 转换失败或空结果：一句话说明影响，然后继续。
- **任务量大时持续执行**：每批 10–20 个文件，批间简短汇报进度，然后继续下一批，直到完成。

### 阶段 5：交付与汇报

- 产出结果文件并 `present_files`。
- 汇报附 token 收益：原文档直读约 X → 瘦身后约 Y，降幅 Z%。

## 可选：三级确认流程（仅当用户显式要求时启用）

**默认不启用。** 仅当用户明确说「我要确认转换内容」「逐个检查」「先让我看看转得对不对」时，在阶段 2/3 之后插入确认环节，用 AskUserQuestion 询问：

- question：`文档已转换为 Markdown（共 N 个）。你希望如何确认转换内容？`
- header：`确认方式`

| 选项 label | description |
|---|---|
| 逐项确认全部 | 我逐个展示每个文件的转换内容，你逐一确认是否有误 |
| 选择部分确认 | 你勾选需要确认的文件，我只展示这些 |
| 无需确认，继续任务 | 跳过内容确认，直接执行任务 |

- **A 逐项确认**：逐个 Read .md 展示；每次问 `「<文件名>」的转换内容是否有误？`（`无误，继续` / `有误，需处理`）。有误则记录，不立即重转。
- **B 选择部分确认**：AskUserQuestion（multiSelect=true）勾选文件，仅对勾选项执行 A。
- **C 无需确认**：直接进入阶段 4。
- 确认结束后照常执行最初任务，不重复询问。

## 命令参考

以下 `$PY` / `$SD` 按「环境准备」解析；本机若已有 `md2md` / `pdf2md` / `slim2md` 命令（PATH 中），可直接替代。

```bash
# 转换
"$PY" "$SD/scripts/mdconvert.py" 文件.docx                          # 原地生成 .md
"$PY" "$SD/scripts/mdconvert.py" ~/docs -r --ext docx xlsx pptx pdf # 目录递归
"$PY" "$SD/scripts/pdf2md.py" 文件.pdf                              # PDF 判别 + 扫描件渲染
"$PY" "$SD/scripts/pdf2md.py" 文件.pdf --scale 4                    # 提高渲染精度

# 瘦身
"$PY" "$SD/scripts/slim.py" ~/docs -r                               # 报告降幅（不写入）
"$PY" "$SD/scripts/slim.py" ~/docs -r --index                       # + 生成薄索引
"$PY" "$SD/scripts/slim.py" ~/docs -r --inplace                     # 原地覆盖优化结果
"$PY" "$SD/scripts/slim.py" 文件.md --no-norm-dedup                 # 关闭某项优化

# 其他
"$PY" "$SD/scripts/mdconvert.py" 文件.docx --stdout                 # 打印不落盘
"$PY" "$SD/scripts/mdconvert.py" ~/docs -r --json                   # 机器可读结果
"$PY" "$SD/scripts/pdf2md.py" 文件.pdf --min-chars 50               # 调整扫描页判别阈值
```

常用参数速查：`-r` 递归目录；`--ext` 限定扩展名；`-o DIR` 指定输出目录（保持相对结构）；`--stdout` 只打印；`--json` 机器可读；`--overwrite` 允许覆盖（默认永不覆盖）。

## 支持与限制

- 稳定支持：pdf（文本型 + 扫描型 + 混合型）、docx、xlsx、xls、pptx、ppt(部分)、html、csv、tsv、json、xml、epub、zip、txt、md、ipynb、msg(Outlook.msg)、图片(jpg/png 等，输出元数据而非 OCR)。
- 扫描件为图片识别路径：渲染 PNG 后由 AI 读取转写，不上传外部服务。
- 识别局限：手写体、严重倾斜模糊、印章遮挡可能出错；无法辨认标注 `[无法辨认]`，不猜测。
- 瘦身局限：**保守优先**，表格与结构行永不参与去重；诗歌、代码类文档建议关闭重连与去重。
- 不支持/需额外 extras：音频转写（`audio-transcription`）、YouTube 字幕（`youtube-transcription`）、Azure 文档智能（`az-doc-intel`，需云端凭据）。
- 平台差异：Linux / Windows 均支持（路径写法见「环境准备」）；Windows 上首次运行如遇 `magika` 模型下载失败，检查代理设置后重试即可，模型会缓存。

## 故障排查

| 现象 | 原因 | 处理 |
|---|---|---|
| `No module named markitdown` | 用错了解释器 | 按「环境准备」解析 `$PY`；不要用系统 Python 直接跑 |
| 安装卡住十几分钟 | Python 3.14 + onnxruntime 无 wheel 导致回溯 | 改用 3.10–3.13 建 venv；勿用 3.14 |
| `could not compile cryptography` | ≥47 仅 arm64 wheel | 约束 `cryptography<=46.0.3`（仅 Intel Mac 需要） |
| opencv 无匹配版本 | 5.0 仅 `macosx_14_0_x86_64` | 约束 `opencv-python-headless==4.11.0.86`（仅 Intel Mac + macOS 13 需要） |
| 转换结果为空 / `chars` 极少 | 阈值误判或加密文档 | 调 `--min-chars`；加密 PDF 先解密 |
| 瘦身后内容缺失 | 误开了某优化 | 表格永不丢失；若正文缺失，用 `--no-norm-dedup` 关闭归一化去重复核 |
| 扫描页识别质量差 | 渲染精度不足或原图模糊 | `--scale 4`；仍差则告知用户原文件质量限制 |
| 首次运行约 40 秒 | 下载 magika 模型 | 正常现象，仅首次；之后约 8 秒 |
