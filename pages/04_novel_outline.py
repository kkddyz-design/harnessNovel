"""新小说大纲生成页面。"""

import os

import streamlit as st
from ui.utils import render_sidebar, capture_stdout, show_logs, read_file_content, workspace_selector, render_bottom_log_panel, render_config_button

render_sidebar()
render_config_button()

st.title("📋 新小说大纲生成")

ws = workspace_selector()
if ws is None:
    st.info("请先在「工作区管理」中创建一个工作区。")
    st.stop()

# ── 参考小说大纲预览 ──
ref_outline = read_file_content(os.path.join(ws.reference, "outlines", "novel_outline.md"))
if ref_outline:
    with st.expander("📖 参考小说大纲"):
        st.markdown(ref_outline)

# ── 创作方向 ──
st.markdown("### ✏️ 创作方向")
direction = st.text_area(
    "描述你想要的创作方向（如：修仙+系统流、都市+重生等）",
    placeholder="例如：保留修仙世界框架，但主角从剑修改为阵法师，增加科技文明入侵的冲突线...",
    height=150,
)
direction_file = st.text_input("或上传创作方向文件路径（可选）")

# ── 大纲设计规则 ──
outline_rules_path = os.path.join(ws.file_system, "OUTLINE_RULES.md")
outline_rules = read_file_content(outline_rules_path)
if outline_rules:
    with st.expander("📐 大纲设计规则（OUTLINE_RULES.md）"):
        st.markdown(outline_rules)

force = st.checkbox("强制重新生成（覆盖已有）")

# ── 生成 ──
if st.button("🚀 生成新小说大纲", type="primary", disabled=(not direction and not direction_file)):
    from training.adaptive_builder import gen_novel_outline

    with st.status("正在生成新小说大纲...", expanded=True) as status_ctx:
        with capture_stdout() as buf:
            gen_novel_outline(
                ws,
                force=force,
                creative_direction=direction or None,
                direction_file=direction_file or None,
            )
        show_logs(buf.getvalue())
        status_ctx.update(label="大纲生成完成！", state="complete")

    st.success("新小说大纲已生成！")

    # 显示结果
    new_outline = read_file_content(os.path.join(ws.file_system, "novel_outline.md"))
    if new_outline:
        st.markdown("### 📄 生成的新小说大纲")
        st.markdown(new_outline)

    new_worldview = read_file_content(os.path.join(ws.file_system, "new_novel_worldview.md"))
    if new_worldview:
        with st.expander("🌍 新小说世界观"):
            st.markdown(new_worldview)

    st.rerun()
else:
    # 已经有的大纲
    existing_outline = read_file_content(os.path.join(ws.file_system, "novel_outline.md"))
    if existing_outline:
        st.markdown("### 📄 当前小说大纲")
        st.markdown(existing_outline)

    existing_worldview = read_file_content(os.path.join(ws.file_system, "new_novel_worldview.md"))
    if existing_worldview:
        with st.expander("🌍 当前小说世界观"):
            st.markdown(existing_worldview)

render_bottom_log_panel()
