"""Streamlit UI 通用工具。"""

import io
import os
import sys
import time
import queue
import threading
from contextlib import contextmanager

import streamlit as st
from log.logger import get_logger


# ── stdout 重定向 ──

@contextmanager
def capture_stdout():
    """捕获函数内的 print() 输出，返回 StringIO buffer。"""
    buf = io.StringIO()
    old = sys.stdout
    sys.stdout = buf
    try:
        yield buf
    finally:
        sys.stdout = old


class TeeStdout(io.StringIO):
    """同时写入 StringIO 和线程安全队列，支持实时读取输出。"""

    def __init__(self, q):
        super().__init__()
        self._q = q

    def write(self, s):
        super().write(s)
        if s.strip():
            self._q.put(s)

    def flush(self):
        pass


# ── 工作区状态检测 ──

def get_workspace_status(ws):
    """检测工作区各步骤完成状态。"""
    fs = ws.file_system
    status = {
        "reference_imported": os.path.exists(ws.reference_sample),
        "novel_outline": os.path.exists(os.path.join(fs, "novel_outline.md")),
        "volume_outline": os.path.exists(os.path.join(fs, "volume_outline.md")),
        "chapter_outlines": False,
        "chapters": False,
    }
    co_dir = os.path.join(fs, "chapter_outlines")
    if os.path.isdir(co_dir):
        status["chapter_outlines"] = len([f for f in os.listdir(co_dir) if f.endswith(".md")]) > 0
    ch_dir = os.path.join(fs, "chapters")
    if os.path.isdir(ch_dir):
        status["chapters"] = len([f for f in os.listdir(ch_dir) if f.endswith(".md")]) > 0
    return status


# ── Sidebar 渲染 ──

def render_sidebar():
    """渲染全局 sidebar：工作区选择 + 状态摘要。"""
    from core.workspace import list_novels, init_workspace

    st.sidebar.markdown("## 📌 当前工作区")

    novels = list_novels()
    if not novels:
        st.sidebar.info("暂无工作区，请先前往「工作区管理」创建。")
        return None, {}

    current = st.session_state.get("active_workspace", None)
    if current not in novels:
        current = novels[0]
        st.session_state.active_workspace = current

    selected = st.sidebar.selectbox(
        "选择工作区",
        novels,
        index=novels.index(current) if current in novels else 0,
        label_visibility="collapsed",
    )
    st.session_state.active_workspace = selected

    ws = init_workspace(selected)
    status = get_workspace_status(ws)

    st.sidebar.markdown("---")
    st.sidebar.markdown("### ⚡ 完成状态")

    steps = [
        ("📥 导入参考小说", "reference_imported"),
        ("📋 新小说大纲", "novel_outline"),
        ("📖 卷纲", "volume_outline"),
        ("📝 章纲", "chapter_outlines"),
        ("✍️ 正文", "chapters"),
    ]
    for label, key in steps:
        icon = "✅" if status[key] else "⏳"
        st.sidebar.markdown(f"{icon} {label}")

    return ws, status


def workspace_selector(default_ws=None):
    """工作区选择器（页面顶部使用），返回选中的 NovelWorkspace。"""
    from core.workspace import list_novels, init_workspace

    novels = list_novels()
    if not novels:
        return None

    current = default_ws.name if default_ws else st.session_state.get("active_workspace", novels[0])
    if current not in novels:
        current = novels[0]

    selected = st.selectbox("工作区", novels, index=novels.index(current))
    st.session_state.active_workspace = selected
    return init_workspace(selected)


def detect_encoding(raw_bytes):
    """自动检测字节串的文本编码。按优先级尝试常见中文编码。"""
    if raw_bytes[:3] == b"\xef\xbb\xbf":
        return "utf-8-sig", True
    if raw_bytes[:2] == b"\xff\xfe":
        return "utf-16-le", True
    if raw_bytes[:2] == b"\xfe\xff":
        return "utf-16-be", True

    candidates = ["utf-8", "gb18030", "gbk", "big5", "latin-1"]
    for enc in candidates:
        try:
            raw_bytes.decode(enc)
            return (enc, enc != "latin-1")
        except (UnicodeDecodeError, UnicodeError):
            continue
    return ("utf-8", False)


def read_file_content(path):
    """读取文件内容，不存在返回 None。"""
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception:
        return None


def show_logs(log_text):
    """在可折叠区域显示日志。"""
    if log_text and log_text.strip():
        with st.expander("📋 详细日志"):
            st.code(log_text)


def render_config_button():
    """在页面右上角渲染齿轮配置按钮。"""
    _, right = st.columns([0.95, 0.05])
    with right:
        if st.button("⚙", key="gear_config_btn", help="模型配置"):
            config_dialog()


@st.dialog("⚙️ 模型配置")
def config_dialog():
    """模型配置对话框：三组配置 + 保存 + 测试连接。"""
    import os

    GLOBAL_CONFIG_DIR = os.path.join(os.path.expanduser("~"), ".harnessNovel")
    GLOBAL_ENV_PATH = os.path.join(GLOBAL_CONFIG_DIR, ".env")

    def _read_config():
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

    config_groups = [
        {
            "title": "拆书模型",
            "help": "参考小说批次摘要提取，建议使用 flash 模型（便宜快速）",
            "prefix": "DATA_BUILDER",
            "default_model": "deepseek-chat",
            "default_url": "https://api.deepseek.com",
        },
        {
            "title": "仿写核心模型",
            "help": "大纲、卷纲、章纲、正文生成，建议使用 pro 模型（高质量）",
            "prefix": "ADAPTIVE_BUILDER",
            "default_model": "deepseek-chat",
            "default_url": "https://api.deepseek.com",
        },
        {
            "title": "仿写辅助模型",
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
                "模型",
                value=existing.get(f"{pfx}_MODEL", group["default_model"]),
                key=f"dialog_{pfx}_model",
            )
        with col2:
            base_url = st.text_input(
                "接口地址",
                value=existing.get(f"{pfx}_BASE_URL", group["default_url"]),
                key=f"dialog_{pfx}_url",
            )
        with col3:
            api_key = st.text_input(
                "密钥",
                value=existing.get(f"{pfx}_API_KEY", ""),
                type="password",
                key=f"dialog_{pfx}_key",
            )

        new_config[f"{pfx}_MODEL"] = model
        new_config[f"{pfx}_BASE_URL"] = base_url
        new_config[f"{pfx}_API_KEY"] = api_key

        has_key = api_key not in ("", "your-api-key")
        if has_key:
            st.success("已配置")
        else:
            st.warning("未配置")
        st.markdown("---")

    # ── 保存配置 ──
    if st.button("💾 保存配置", key="dialog_save_config", use_container_width=True):
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
    st.markdown("---")
    st.caption("🔌 测试连接")
    test_group = st.selectbox(
        "选择配置组",
        [g["title"] for g in config_groups],
        key="dialog_test_group",
        label_visibility="collapsed",
    )
    if st.button("发送测试请求", key="dialog_test_conn"):
        idx = [g["title"] for g in config_groups].index(test_group)
        pfx = config_groups[idx]["prefix"]
        model_val = new_config.get(f"{pfx}_MODEL", "")
        url_val = new_config.get(f"{pfx}_BASE_URL", "")
        key_val = new_config.get(f"{pfx}_API_KEY", "")

        log = get_logger()
        log.info(f"测试连接：group={test_group}, model={model_val}, base_url={url_val}")

        if not key_val or key_val == "your-api-key":
            st.error("密钥未填写或仍为占位符")
        elif not url_val:
            st.error("接口地址未填写")
        else:
            try:
                from core.llm_provider import LLMProvider

                llm = LLMProvider(model=model_val, base_url=url_val, api_key=key_val)
                with st.spinner("正在请求模型..."):
                    result = llm.generate("请用一句中文回复：你好，我是harnessNovel。", temperature=0.3)
                st.success("连接成功！")
                log.success(f"测试连接成功，模型返回：{result[:200]}")
                st.markdown(f"模型回复：\n\n{result}")
            except Exception as e:
                st.error(f"连接失败：{e}")

    # ── 返回 ──
    st.markdown("---")
    if st.button("← 返回主页面", key="dialog_back", use_container_width=True):
        st.rerun()


def render_bottom_log_panel():
    """在页面底部渲染 LM Studio 风格可展开日志面板。"""
    lm = get_logger()
    log_text = lm.get_all_text(200)

    with st.expander("📜 日志", expanded=False):
        col1, col2 = st.columns([4, 1])
        with col2:
            if st.button("🔄 清空日志", use_container_width=True):
                lm.clear()
                st.rerun()
        with col1:
            st.caption(f"全局运行日志（最近 200 条）")

        st.markdown(
            f"""<div style="max-height:400px;overflow-y:auto;background:#1e1e1e;color:#d4d4d4;
            font-size:12px;font-family:monospace;padding:10px;border-radius:6px;
            white-space:pre-wrap;word-break:break-all;line-height:1.5">
{log_text or "暂无日志"}</div>""",
            unsafe_allow_html=True,
        )
