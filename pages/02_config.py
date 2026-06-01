"""配置管理页面。"""

import os

import streamlit as st
from ui.utils import render_sidebar
from log.logger import get_logger

render_sidebar()
log = get_logger()

GLOBAL_CONFIG_DIR = os.path.join(os.path.expanduser("~"), ".harnessNovel")
GLOBAL_ENV_PATH = os.path.join(GLOBAL_CONFIG_DIR, ".env")

st.title("⚙️ 配置管理")

st.markdown("配置 LLM API 连接参数。配置将保存到 `~/.harnessNovel/.env`。")


def _read_config():
    """读取现有配置文件。"""
    config = {}
    for env_path in [os.path.join(os.getcwd(), ".env"), GLOBAL_ENV_PATH]:
        if not os.path.exists(env_path):
            continue
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                config[key.strip()] = value.strip()
    return config


existing = _read_config()

# ── 三组配置 ──
config_groups = [
    {
        "title": "Data Builder（拆书）",
        "help": "参考小说批次摘要提取，建议使用 flash 模型（便宜快速）",
        "prefix": "DATA_BUILDER",
        "default_model": "deepseek-chat",
        "default_url": "https://api.deepseek.com",
    },
    {
        "title": "Adaptive Builder（仿写核心）",
        "help": "大纲、卷纲、章纲、正文生成，建议使用 pro 模型（高质量）",
        "prefix": "ADAPTIVE_BUILDER",
        "default_model": "deepseek-chat",
        "default_url": "https://api.deepseek.com",
    },
    {
        "title": "Adaptive Builder Lite（仿写辅助）",
        "help": "世界观提取等辅助任务，建议使用 flash 模型",
        "prefix": "ADAPTIVE_BUILDER_LITE",
        "default_model": "deepseek-chat",
        "default_url": "https://api.deepseek.com",
    },
]

new_config = {}

for group in config_groups:
    pfx = group["prefix"]
    st.markdown(f"### {group['title']}")
    st.caption(group["help"])

    col1, col2, col3 = st.columns(3)
    with col1:
        model = st.text_input(
            "MODEL",
            value=existing.get(f"{pfx}_MODEL", group["default_model"]),
            key=f"{pfx}_model",
        )
    with col2:
        base_url = st.text_input(
            "BASE_URL",
            value=existing.get(f"{pfx}_BASE_URL", group["default_url"]),
            key=f"{pfx}_url",
        )
    with col3:
        api_key = st.text_input(
            "API_KEY",
            value=existing.get(f"{pfx}_API_KEY", ""),
            type="password",
            key=f"{pfx}_key",
        )

    new_config[f"{pfx}_MODEL"] = model
    new_config[f"{pfx}_BASE_URL"] = base_url
    new_config[f"{pfx}_API_KEY"] = api_key

    # 显示当前状态（优先检查当前输入框的值）
    has_key = api_key not in ("", "your-api-key")
    if has_key:
        st.success("已配置")
    else:
        st.warning("未配置")
    st.markdown("---")

# ── 保存按钮 ──
if st.button("💾 保存配置", type="primary"):
    os.makedirs(GLOBAL_CONFIG_DIR, exist_ok=True)
    lines = [
        "# harnessNovel LLM 配置",
        f"DATA_BUILDER_MODEL={new_config['DATA_BUILDER_MODEL']}",
        f"DATA_BUILDER_BASE_URL={new_config['DATA_BUILDER_BASE_URL']}",
        f"DATA_BUILDER_API_KEY={new_config['DATA_BUILDER_API_KEY']}",
        "",
        f"ADAPTIVE_BUILDER_MODEL={new_config['ADAPTIVE_BUILDER_MODEL']}",
        f"ADAPTIVE_BUILDER_BASE_URL={new_config['ADAPTIVE_BUILDER_BASE_URL']}",
        f"ADAPTIVE_BUILDER_API_KEY={new_config['ADAPTIVE_BUILDER_API_KEY']}",
        "",
        f"ADAPTIVE_BUILDER_LITE_MODEL={new_config['ADAPTIVE_BUILDER_LITE_MODEL']}",
        f"ADAPTIVE_BUILDER_LITE_BASE_URL={new_config['ADAPTIVE_BUILDER_LITE_BASE_URL']}",
        f"ADAPTIVE_BUILDER_LITE_API_KEY={new_config['ADAPTIVE_BUILDER_LITE_API_KEY']}",
        "",
    ]
    with open(GLOBAL_ENV_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    st.success(f"配置已保存到 {GLOBAL_ENV_PATH}")

# ── 测试连接 ──
st.markdown("### 🔌 测试连接")
test_group = st.selectbox("选择要测试的配置组", [g["title"] for g in config_groups])
if st.button("发送测试请求"):
    idx = [g["title"] for g in config_groups].index(test_group)
    pfx = config_groups[idx]["prefix"]

    model = new_config.get(f"{pfx}_MODEL", "")
    base_url = new_config.get(f"{pfx}_BASE_URL", "")
    api_key = new_config.get(f"{pfx}_API_KEY", "")

    log.info(f"测试连接：group={test_group}, model={model}, base_url={base_url}")
    log.info(f"api_key 长度={len(api_key)}, 是否为空={not api_key}, 前4位={api_key[:4] if len(api_key)>=4 else 'N/A'}")

    if not api_key or api_key == "your-api-key":
        st.error("API Key 未填写或仍为占位符，请先填入真实的 API Key 并保存。")
        log.error("测试连接中止：api_key 无效")
    elif not base_url:
        st.error("BASE_URL 未填写。")
        log.error("测试连接中止：base_url 为空")
    else:
        try:
            from core.llm_provider import LLMProvider

            llm = LLMProvider(model=model, base_url=base_url, api_key=api_key)
            with st.spinner("正在请求模型..."):
                result = llm.generate("请用一句中文回复：你好，我是harnessNovel。", temperature=0.3)

            st.success("连接成功！")
            log.success(f"测试连接成功，模型返回：{result[:200]}")
            st.markdown(f"模型回复：\n\n{result}")
        except Exception as e:
            st.error(f"连接失败：{e}")
            log.error(f"测试连接异常：{type(e).__name__}: {e}")
