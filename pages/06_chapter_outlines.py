"""章纲生成页面。"""

import os

import streamlit as st
from ui.utils import render_sidebar, capture_stdout, show_logs, read_file_content, workspace_selector

render_sidebar()

st.title("📝 章纲生成")

ws = workspace_selector()
if ws is None:
    st.info("请先在「工作区管理」中创建一个工作区。")
    st.stop()

col1, col2 = st.columns(2)
with col1:
    volume = st.number_input("卷号", min_value=1, value=1, step=1)
with col2:
    force = st.checkbox("强制重新生成")

# ── 已生成章纲 ──
chapter_outlines_dir = os.path.join(ws.file_system, "chapter_outlines")
if os.path.isdir(chapter_outlines_dir):
    existing = sorted([f for f in os.listdir(chapter_outlines_dir) if f.endswith(".md")])
    if existing:
        st.markdown(f"### 已生成章纲（{len(existing)} 个）")
        cols_per_row = 3
        for i in range(0, len(existing), cols_per_row):
            cols = st.columns(cols_per_row)
            for j in range(cols_per_row):
                idx = i + j
                if idx < len(existing):
                    with cols[j]:
                        content = read_file_content(os.path.join(chapter_outlines_dir, existing[idx]))
                        preview = content[:200] + "..." if content and len(content) > 200 else (content or "")
                        with st.expander(existing[idx]):
                            if content:
                                st.markdown(content)

# # ── 批次摘要 ──
# outlines_dir = os.path.join(ws.file_system, "outlines")
# if os.path.isdir(outlines_dir):
#     batches = sorted([f for f in os.listdir(outlines_dir) if f.endswith(".md")])
#     if batches:
#         with st.expander(f"📊 批次摘要（{len(batches)} 个）"):
#             for bn in batches:
#                 batch_content = read_file_content(os.path.join(outlines_dir, bn))
#                 if batch_content:
#                     st.markdown(f"**{bn}**")
#                     st.markdown(batch_content[:500])
#                     st.markdown("---")

# ── 生成 ──
if st.button("🚀 生成章纲", type="primary"):
    from training.adaptive_builder import gen_serial_chapter_outlines

    with st.status("正在生成章纲（两阶段：批次摘要 → 逐章章纲）...", expanded=True) as status_ctx:
        with capture_stdout() as buf:
            gen_serial_chapter_outlines(ws, volume=volume, force=force)
        show_logs(buf.getvalue())
        status_ctx.update(label="章纲生成完成！", state="complete")

    st.success(f"第 {volume} 卷章纲已生成！")
    st.rerun()
