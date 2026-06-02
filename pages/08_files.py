"""文件浏览页面。"""

import os

import streamlit as st
from ui.utils import render_sidebar, read_file_content, workspace_selector, render_bottom_log_panel, render_config_button

render_sidebar()
render_config_button()

st.title("📂 文件浏览")

ws = workspace_selector()
if ws is None:
    st.info("请先在「工作区管理」中创建一个工作区。")
    st.stop()

# ── 收集所有文件 ──
def collect_files(base_dir, prefix=""):
    """递归收集目录下所有 .md/.txt 文件。"""
    files = []
    try:
        for item in sorted(os.listdir(base_dir)):
            full = os.path.join(base_dir, item)
            rel = os.path.join(prefix, item) if prefix else item
            if os.path.isdir(full):
                files.extend(collect_files(full, rel))
            elif item.endswith((".md", ".txt")):
                files.append((rel, full))
    except PermissionError:
        pass
    return files


all_files = collect_files(ws.root)
all_files.sort(key=lambda x: x[0])

if not all_files:
    st.info("工作区暂无文件。")
    st.stop()

# ── 文件树 ──
st.markdown(f"### 工作区 `{ws.name}` 文件列表（{len(all_files)} 个）")

selected_file = st.selectbox(
    "选择文件",
    all_files,
    format_func=lambda x: x[0],
    label_visibility="collapsed",
)

if selected_file:
    rel_path, abs_path = selected_file
    content = read_file_content(abs_path)

    st.markdown(f"**路径**: `{rel_path}`")
    st.markdown(f"**大小**: {os.path.getsize(abs_path):,} 字节")

    if content:
        is_md = rel_path.endswith(".md")
        max_display = 5000

        if len(content) > max_display:
            st.caption(f"文件较大，仅显示前 {max_display} 字。")
            content = content[:max_display] + "\n\n...(内容过长，已截断)"

        if is_md:
            st.markdown("---")
            st.markdown(content)
        else:
            st.markdown("---")
            st.code(content, language="text")
    else:
        st.warning("无法读取文件内容。")

render_bottom_log_panel()
