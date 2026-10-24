[English](README.en.md) | 简体中文
# doc2md Token Slim

把大量文档（PDF、Word、Excel、PPT、HTML、CSV、JSON、EPUB、ZIP、Outlook 等）批量转换为 Markdown，并做 **token 瘦身**，再由 AI 基于瘦身后的输出直接执行完整任务——全程自动，不中断。

> 转换是手段，完成任务才是目的。

## 为什么不直接用 markitdown？

知名的 `markitdown` 技能/库做的是格式转换。本技能是**不同的东西**，为 AI token 效率而构建：

| 维度 | markitdown | **doc2md-token-slim** |
|---|---|---|
| 目标 | 格式转换 | **转换 + 降 token**，随后直接执行你的任务 |
| 扫描件 PDF | 通常产出空内容 | 逐页判别 + 高清渲染 + AI 识别（中文实测 100% 准确） |
| token 优化 | 无 | 四重瘦身：断行重连 / 页眉页脚移除 / 归一化去重 / 薄索引 |
| 混合 PDF（文本页 + 扫描页） | 不处理 | 逐页判别；文本页直接抽取，扫描页识别转写，结果合并 |
| 执行模式 | 转换即止 | 转换后**直接执行你的任务**，分批持续推进到完成 |
| 量化验证 | 无 | 提供实测数据与可复现脚本 |

## 实测 token 降幅

| 方法 | 实测效果 |
|---|---|
| Markdown 转换（剥离 Office XML / PDF 版式噪音） | Office 文件约 **80%**，扫描 PDF 约 **73%** |
| 归一化去重（折叠跨页重复的模板句） | 模板化 PDF 最高 **98.7%** |
| 页眉页脚移除（跨页标题栏、页码、保密声明） | 幻灯片类 **61.6%** |
| 断行重连（PDF「一行一句」→ 完整段落） | 视源文件而定 |
| 薄索引 + 按需读取 | 常驻成本从全文降为几 KB 索引 |
| 扫描页图片识别（图片 → 文字） | 每页 **2,898 → 783** tokens |

明确**不采用**的方法：LLMLingua / Selective Context（按 token 粒度删除会砍断参数名、不保证语义连贯）、向量 RAG（由零依赖的「薄索引 + 关键词定位」替代）、Prompt Caching（属调用方 API 侧优化，本地转换层无法控制）。

## 支持格式

pdf（文本型 / 扫描型 / 混合型）、docx、xlsx、xls、pptx、ppt（部分）、html、csv、tsv、json、xml、epub、zip、txt、md、ipynb、msg（Outlook）、图片（jpg/png 等——输出元数据，不做 OCR）。

## 环境准备（一次）

要求：**Python 3.10–3.13**。**不要用 3.14** —— 核心依赖 `magika` 依赖 `onnxruntime`，而 onnxruntime 没有 3.14 的 wheel，pip 会陷入依赖回溯卡死。

```bash
SD="<技能安装目录>"                                # SKILL.md 所在目录
VENV="$HOME/.cache/doc2md-token-slim/venv"         # Windows: %LOCALAPPDATA%\doc2md-token-slim\venv
python3.13 -m venv "$VENV"                         # 或 python3.12 / python3.11

# Intel Mac 必需的版本约束（其他平台可选）
cat > /tmp/doc2md-constraints.txt <<'EOF'
cryptography<=46.0.3
opencv-python-headless==4.11.0.86
EOF

# 安装（uv 快约一个数量级；也可用 venv 内的 pip）
uv pip install --python "$VENV/bin/python" -c /tmp/doc2md-constraints.txt \
  "markitdown[pdf,docx,xlsx,xls,pptx,outlook]" pypdfium2 pdfplumber tiktoken
```

依赖分工：`markitdown`（转换核心）、`pdfplumber`（PDF 逐页判别）、`pypdfium2`（扫描页高清渲染）、`tiktoken`（token 估算，缺失时自动降级为字数估算）。

## 用法

```bash
PY="$VENV/bin/python"    # Windows: $VENV\Scripts\python.exe

# 转换非 PDF 文档
"$PY" "$SD/scripts/mdconvert.py" /path/to/docs -r --ext docx xlsx pptx html csv json txt --json

# 转换 PDF（逐页文本/扫描判别 + 渲染）
"$PY" "$SD/scripts/pdf2md.py" /path/to/docs -r --json

# token 瘦身（只报告降幅，不写入）
"$PY" "$SD/scripts/slim.py" /path/to/docs -r

# 瘦身 + 生成 INDEX.md 薄索引
"$PY" "$SD/scripts/slim.py" /path/to/docs -r --index

# 原地覆盖写入瘦身结果
"$PY" "$SD/scripts/slim.py" /path/to/docs -r --inplace

# 关闭某项优化（如诗歌、代码类文档）
"$PY" "$SD/scripts/slim.py" file.md --no-norm-dedup
```

常用参数：`-r` 递归；`--ext` 限定扩展名；`-o DIR` 指定输出目录（保持相对结构）；`--stdout` 只打印；`--json` 机器可读；`--overwrite` 允许覆盖（默认永不覆盖）；`--scale 4` 提高渲染精度；`--min-chars` 调整扫描页判别阈值。

首次运行会下载 magika 模型（约 40 秒，仅一次），之后单次约 8 秒。

### 安全保障

- **永不覆盖**已有文件（除非加 `--overwrite`）。
- 保守瘦身：**表格行、标题、列表、代码块一律不参与**合并与去重——实测 400 行表格数据零丢失。
- 无法辨认的扫描文字标注 `[无法辨认]`，绝不猜测。
- 扫描页在本地渲染并由 AI 直接识别——不上传任何外部服务。

## 典型指令示例

- 「把 ~/Documents/2026报告/ 下的 docx、xlsx、pptx 全部转成 md，保存在原文件同目录下。」
- 「这个文件夹里混着扫描版 PDF，帮我逐页判别，扫描页识别成 md 后，再汇总所有设备的维保记录做一张对比表。」
- 「把这 300 页技术文档转成 md 并瘦身，我要控制 token 消耗。」

## 故障排查

| 现象 | 原因 | 处理 |
|---|---|---|
| `No module named markitdown` | 用错了解释器 | 按「环境准备」解析 `$PY`；不要用系统 Python 直接跑 |
| 安装卡住十几分钟 | Python 3.14 + onnxruntime 无 wheel | 改用 3.10–3.13 重建 venv |
| `could not compile cryptography` | cryptography ≥ 47 仅有 arm64 wheel | 约束 `cryptography<=46.0.3`（仅 Intel Mac） |
| opencv 无匹配版本 | opencv 5.0 仅支持 `macosx_14_0_x86_64` | 约束 `opencv-python-headless==4.11.0.86`（仅 Intel Mac + macOS 13） |
| 转换结果为空 / `chars` 极少 | 阈值误判或加密文档 | 调 `--min-chars`；加密 PDF 先解密 |
| 瘦身后内容缺失 | 某项优化误伤 | 表格永不丢失；正文缺失时用 `--no-norm-dedup` 关闭归一化去重复核 |
| 扫描页识别质量差 | 渲染精度不足或原图模糊 | 用 `--scale 4`；仍差则属源文件质量限制 |
| 首次运行约 40 秒 | 下载 magika 模型 | 正常现象，仅首次；之后约 8 秒 |

Windows 上首次运行如遇 magika 模型下载失败，检查代理设置后重试即可，模型会缓存。

## 许可证

见 [LICENSE](LICENSE)。
