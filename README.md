# harnessNovel

长篇网络小说AI仿写系统，通过多轮 LLM 调用实现从拆书分析→大纲→卷纲→章纲→正文的自动化生成。

## 执行环境

- Python 3.9+
- LLM API：需支持 OpenAI 兼容接口（DeepSeek、智谱 GLM、Kimi 等）

## 安装

```bash
cd harnessNovel
pip3 install -e .
```

安装后 `novel` 命令全局可用。

## 配置

复制 `.env` 模板并填入你的 LLM API 配置：

```bash
cp .env.example .env
```

编辑 `.env`：

```
# 参考小说批次摘要提取（建议 flash 模型）
DATA_BUILDER_MODEL=deepseek-v4-flash
DATA_BUILDER_BASE_URL=https://api.deepseek.com
DATA_BUILDER_API_KEY=your-api-key

# 仿写辅助任务：世界观提取（建议 flash 模型）
ADAPTIVE_BUILDER_LITE_MODEL=deepseek-v4-flash
ADAPTIVE_BUILDER_LITE_BASE_URL=https://api.deepseek.com
ADAPTIVE_BUILDER_LITE_API_KEY=your-api-key

# 仿写核心任务：大纲、卷纲、章纲、正文（建议 pro 模型）
ADAPTIVE_BUILDER_MODEL=deepseek-v4-pro
ADAPTIVE_BUILDER_BASE_URL=https://api.deepseek.com
ADAPTIVE_BUILDER_API_KEY=your-api-key
```

也可通过同名环境变量覆盖 `.env` 中的配置。

## 完整流程

```bash
WS=我的新小说名

# 1. 初始化工作区（自动拆书：章节切分→批次摘要→智能分卷→世界观提取）
novel init WS --txt 参考小说.txt

# 2. 生成新小说大纲 + 全书世界观
novel novel-outline WS
# 可指定创作方向：
# novel novel-outline $WS --direction "改为现代都市背景"
# novel novel-outline $WS --direction-file 方向.txt

# 3. 生成卷纲 + 每卷世界观（逐卷）
novel volume-outline WS --volume 1

# 4. 生成章纲（两阶段：批次摘要 → 逐章章纲）
novel chapter-outlines WS --volume 1

# 5. 生成正文
novel write WS --volume 1
```

## 命令参考

| 命令                                                    | 说明               |
| ----------------------------------------------------- | ---------------- |
| `novel list`                                          | 列出所有工作区          |
| `novel init <ws> --txt <path>`                        | 创建工作区，自动拆书+世界观提取 |
| `novel novel-outline <ws>`                            | 生成新小说大纲和全书世界观    |
| `novel volume-outline <ws> [--volume N]`              | 生成卷纲和每卷世界观       |
| `novel chapter-outlines <ws> [--volume N]`            | 生成批次摘要和逐章章纲      |
| `novel write <ws> [--volume N] [--start N] [--max N]` | 串行生成正文           |

## License

GPL-3.0
