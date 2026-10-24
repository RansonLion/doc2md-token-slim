# doc2md-token-slim

文档批量转 Markdown 并做 token 瘦身的 GLM Skill。把大量文档（PDF / Word / Excel / PPT / HTML / CSV / JSON / EPUB / ZIP / Outlook 等）批量转为 Markdown，再由 AI 基于瘦身后的 md 直接执行任务，全程自动不中断。

## 核心能力

- **PDF 逐页判别**：自动区分文本型页与扫描型页；扫描页渲染为高清 PNG 由 AI 识别转写
- **Token 瘦身**：断行重连、页眉页脚移除、跨页模板句归一化去重，生成薄索引 `INDEX.md` 实现按需取全文
- **实测降幅**：Office 约 80%、扫描 PDF 约 73%、模板化 PDF 去重后最高 98.7%

## 环境要求

- Python 3.10–3.13（不要用 3.14：onnxruntime 无可用 wheel）
- 依赖：markitdown、pdfplumber、pypdfium2、tiktoken、magika 等（安装于独立 venv，不污染系统环境）
- Windows / macOS / Linux 通用

## 使用方式

将本仓库整体放置于技能目录（如 `~/.workbuddy/skills/doc2md-token-slim`），由支持 Skills 协议的 AI 助手加载 `SKILL.md` 后按其中的工作流调用 `scripts/` 下的三个脚本：

| 脚本 | 用途 |
|---|---|
| `scripts/mdconvert.py` | 各类文档 → Markdown（原地输出，默认永不覆盖已有文件） |
| `scripts/pdf2md.py` | PDF 逐页判别，扫描页渲染高清 PNG + 待识别清单 |
| `scripts/slim.py` | token 瘦身：断行重连 / 页眉页脚移除 / 去重 / 薄索引 |

## 安全说明

- 全部本地处理，扫描件渲染 PNG 后由 AI 读取转写，不上传外部服务
- 脚本无网络请求、无遥测；唯一联网行为是首次运行时 pip 依赖与 magika 模型下载（约 40 秒，一次性）
- 写盘仅限源目录生成 `.md` 与渲染产物；渲染产物清理前会先询问用户

## 许可证

MIT License，详见 [LICENSE](LICENSE)。
