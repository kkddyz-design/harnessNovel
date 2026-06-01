"""卷纲生成页面。"""

import os

import streamlit as st
from ui.utils import render_sidebar, capture_stdout, show_logs, read_file_content, workspace_selector

render_sidebar()

st.title("📖 卷纲生成")

ws = workspace_selector()
if ws is None:
    st.info("请先在「工作区管理」中创建一个工作区。")
    st.stop()

# ── 参考小说卷信息 ──
outlines_dir = os.path.join(ws.reference, "outlines")
try:
    from training.reference_finder import list_reference_volumes

    ref_vols = list_reference_volumes(outlines_dir)
    if ref_vols:
        st.caption(f"参考小说共有 {len(ref_vols)} 卷")
except Exception:
    ref_vols = []

# ── 参数 ──
col1, col2 = st.columns(2)
with col1:
    volume_start = st.number_input("起始卷号", min_value=1, value=1, step=1)
with col2:
    force = st.checkbox("强制重新生成")

direction = st.text_area("补充创作方向（可选）", placeholder="针对本卷的额外创作指示...")

# ── 已生成卷纲 ──
vol_outlines_dir = os.path.join(ws.file_system, "new_volume_outlines")
if os.path.isdir(vol_outlines_dir):
    existing = sorted([f for f in os.listdir(vol_outlines_dir) if f.endswith(".md")])
    if existing:
        st.markdown(f"### 已生成卷纲（{len(existing)} 个）")
        for fn in existing:
            content = read_file_content(os.path.join(vol_outlines_dir, fn))
            if content:
                with st.expander(f"📄 {fn}"):
                    st.markdown(content)

# ── 生成 ──
if st.button("🚀 生成卷纲", type="primary"):
    from training.adaptive_builder import gen_volume_outline

    with st.status("正在生成卷纲...", expanded=True) as status_ctx:
        with capture_stdout() as buf:
            gen_volume_outline(
                ws,
                volume=volume_start if volume_start > 1 else None,
                force=force,
                creative_direction=direction or None,
            )
        show_logs(buf.getvalue())
        status_ctx.update(label="卷纲生成完成！", state="complete")

    st.success("卷纲已生成！")
    st.rerun()

# ── 汇总卷纲 ──
summary = read_file_content(os.path.join(ws.file_system, "volume_outline.md"))
if summary:
    with st.expander("📊 汇总卷纲（volume_outline.md）"):
        st.markdown(summary)
