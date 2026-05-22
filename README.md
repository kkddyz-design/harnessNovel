<p align="center">
  <img src="docs/logo.png" width="100">
  &nbsp;&nbsp;
  <img src="docs/name.png" width="300">
</p>

<h3 align="center">长篇网络小说 AI 仿写系统</h3>

<p align="center">通过多轮 LLM 调用，将一本参考小说自动拆解为大纲→卷纲→批次摘要→章纲→正文，并仿写生成全新的长篇小说。</p>

<div align="center">

[![Python 3.9+](https://img.shields.io/badge/Python-3.9%2B-blue.svg)](https://www.python.org/)
[![License: GPL-3.0](https://img.shields.io/badge/License-GPL--3.0-green.svg)](LICENSE)

</div>

---

## 工作原理

```
参考小说.txt
    │
    ▼  novel init（自动拆书）
┌──────────────────────────────┐
│  章节切分 → 批次摘要 → 智能分卷  │
│         → 世界观提取            │
└──────────────────────────────┘
    │
    ▼  novel novel-outline
┌──────────────────────────────┐
│  参考大纲 + 世界观 + 创作方向     │
│      → 新小说大纲 + 新世界观     │
└──────────────────────────────┘
    │
    ▼  novel volume-outline（逐卷）
┌──────────────────────────────┐
│  新大纲 + 参考卷纲 + 世界观       │
│      → 新卷纲 + 卷世界观         │
└──────────────────────────────┘
    │
    ▼  novel chapter-outlines（两阶段）
┌──────────────────────────────┐
│  阶段1：卷纲 → 批次摘要（每20章） │
│  阶段2：批次摘要 → 逐章章纲       │
└──────────────────────────────┘
    │
    ▼  novel write（逐章生成正文）
┌──────────────────────────────┐
│  卷纲 + 批次摘要 + 前文 + 章纲    │
│         → 正文                 │
└──────────────────────────────┘
```

## 特性

- **全流程自动化**：从拆书分析到正文生成，5 条命令完成完整长篇小说
- **参考仿写**：基于参考小说的节奏、结构、张力曲线生成新内容，而非凭空创作
- **批次摘要**：每 20 章一个批次，保持长线情节连贯性
- **渐进式世界观**：全书世界观 → 每卷世界观，随情节推进细化设定
- **断点续写**：所有阶段自动跳过已生成内容，支持中断后继续

## 环境要求

- Python 3.9+
- LLM API：需支持 OpenAI 兼容接口（DeepSeek、智谱 GLM、Kimi 等）

## 安装

```bash
git clone https://github.com/XTmingyue/harnessNovel.git
cd harnessNovel
pip3 install -e .
```

安装后 `novel` 命令全局可用。

## 配置

复制模板并填入你的 LLM API 配置：

```bash
cp .env.example .env
```

编辑 `.env`：

```ini
# 参考小说批次摘要提取（建议 flash 模型，速度快、成本低）
DATA_BUILDER_MODEL=deepseek-v4-flash
DATA_BUILDER_BASE_URL=https://api.deepseek.com
DATA_BUILDER_API_KEY=your-api-key

# 仿写辅助任务：世界观提取（建议 flash 模型）
ADAPTIVE_BUILDER_LITE_MODEL=deepseek-v4-flash
ADAPTIVE_BUILDER_LITE_BASE_URL=https://api.deepseek.com
ADAPTIVE_BUILDER_LITE_API_KEY=your-api-key

# 仿写核心任务：大纲、卷纲、章纲、正文（建议 pro 模型，质量高）
ADAPTIVE_BUILDER_MODEL=deepseek-v4-pro
ADAPTIVE_BUILDER_BASE_URL=https://api.deepseek.com
ADAPTIVE_BUILDER_API_KEY=your-api-key
```

也可通过同名环境变量覆盖 `.env` 中的配置。三组配置可使用不同的模型和服务商。

## 快速开始

```bash
# 1. 初始化工作区（自动拆书：章节切分→批次摘要→智能分卷→世界观提取）
novel init 我的新小说 --txt 参考小说.txt

# 2. 生成新小说大纲 + 全书世界观
novel novel-outline 我的新小说

# 3. 生成卷纲 + 每卷世界观
novel volume-outline 我的新小说 --volume 1

# 4. 生成批次摘要 + 逐章章纲
novel chapter-outlines 我的新小说 --volume 1

# 5. 生成正文
novel write 我的新小说 --volume 1
```

## 命令参考

| 命令 | 说明 |
|------|------|
| `novel list` | 列出所有工作区 |
| `novel init <ws> --txt <path> [--batch-size N]` | 创建工作区，自动拆书 + 世界观提取 |
| `novel novel-outline <ws> [--direction TEXT] [--direction-file PATH]` | 生成新小说大纲和全书世界观 |
| `novel volume-outline <ws> [--volume N] [--force]` | 生成卷纲和每卷世界观 |
| `novel chapter-outlines <ws> [--volume N] [--force]` | 两阶段生成：批次摘要 → 逐章章纲 |
| `novel write <ws> [--volume N] [--start N] [--max N]` | 串行生成正文 |

### 参数说明

- `--txt <path>`：参考小说文件路径（仅 init）
- `--batch-size N`：每批处理章节数，默认 20（仅 init）
- `--direction TEXT`：创作方向，如"改为现代都市背景"（仅 novel-outline）
- `--direction-file PATH`：从文件读取创作方向（仅 novel-outline）
- `--volume N`：指定卷号，默认 1
- `--start N`：起始章节号，默认 1（仅 write）
- `--max N`：最大生成章节数（仅 write）
- `--force`：强制重新生成，覆盖已有内容

## License

[GPL-3.0](LICENSE)
