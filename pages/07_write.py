"""正文撰写页面。"""

import os

import streamlit as st
from ui.utils import render_sidebar, capture_stdout, show_logs, read_file_content, workspace_selector

render_sidebar()

st.title("✍️ 正文撰写")

ws = workspace_selector()
if ws is None:
    st.info("请先在「工作区管理」中创建一个工作区。")
    st.stop()

col1, col2, col3 = st.columns(3)
with col1:
    volume = st.number_input("卷号", min_value=1, value=1, step=1)
with col2:
    start_chapter = st.number_input("起始章节", min_value=1, value=1, step=1)
with col3:
    max_chapters = st.number_input("最大章节数（0=全部）", min_value=0, value=0, step=1)

# ── 写作规范 ──
agents_path = os.path.join(ws.file_system, "AGENTS.md")
agents_content = read_file_content(agents_path)
if agents_content:
    with st.expander("📐 写作规范（AGENTS.md）"):
        st.markdown(agents_content)

# ── 已生成正文 ──
chapters_dir = os.path.join(ws.file_system, "chapters")
if os.path.isdir(chapters_dir):
    existing = sorted([f for f in os.listdir(chapters_dir) if f.endswith(".md")])
    if existing:
        st.markdown(f"### 已生成正文（{len(existing)} 章）")
        for fn in existing:
            content = read_file_content(os.path.join(chapters_dir, fn))
            if content:
                with st.expander(f"📄 {fn}"):
                    st.markdown(content[:1000])
                    if len(content) > 1000:
                        st.caption(f"...（共 {len(content)} 字）")

# ── 生成 ──
if st.button("🚀 开始撰写", type="primary"):
    from training.adaptive_builder import gen_serial_chapters

    with st.status("正在撰写正文...", expanded=True) as status_ctx:
        with capture_stdout() as buf:
            gen_serial_chapters(
                ws,
                volume=volume,
                start_chapter=start_chapter,
                max_chapters=max_chapters if max_chapters > 0 else None,
            )
        show_logs(buf.getvalue())
        status_ctx.update(label="撰写完成！", state="complete")

    st.success("正文撰写完成！")
    st.rerun()

# ── 动态世界观 ──
dynamic_wv = read_file_content(os.path.join(ws.file_system, "dynamic_worldview.md"))
if dynamic_wv:
    with st.expander("🌍 动态世界观"):
        st.markdown(dynamic_wv)
