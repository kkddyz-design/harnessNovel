"""Streamlit UI 通用工具。"""

import io
import os
import sys
import time
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

    render_log_panel()

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


def render_log_panel():
    """在 sidebar 底部渲染滚动日志面板。"""
    lm = get_logger()
    log_text = lm.get_all_text(100)

    st.sidebar.markdown("---")
    st.sidebar.markdown("### 📜 实时日志")

    if st.sidebar.button("🔄 刷新 / 清空", use_container_width=True):
        lm.clear()
        st.rerun()

    st.sidebar.markdown(
        f"""<div style="height:200px;overflow-y:scroll;background:#1e1e1e;color:#d4d4d4;
        font-size:11px;font-family:monospace;padding:8px;border-radius:4px;
        white-space:pre-wrap;word-break:break-all;line-height:1.4">
{log_text or "暂无日志"}</div>""",
        unsafe_allow_html=True,
    )
