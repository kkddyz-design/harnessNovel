"""导入参考小说页面。"""

import os
import re
import shutil
import sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import streamlit as st
from core.workspace import init_workspace
from ui.utils import render_sidebar, capture_stdout, show_logs, workspace_selector, detect_encoding

render_sidebar()

st.title("📥 导入参考小说")

ws = workspace_selector()
if ws is None:
    st.info("请先在「工作区管理」中创建一个工作区。")
    st.stop()

# ── 当前状态 ──
sample_path = ws.reference_sample
if os.path.exists(sample_path):
    st.success(f"已有参考小说：`{sample_path}`")
    outlines_dir = os.path.join(ws.reference, "outlines")
    vol_dirs = []
    if os.path.isdir(outlines_dir):
        vol_dirs = [d for d in os.listdir(outlines_dir)
                    if re.match(r'^vol_\d+_.+$', d) and os.path.isdir(os.path.join(outlines_dir, d))]
    st.metric("已识别分卷", len(vol_dirs))

st.markdown("---")

# ── 上传文件 ──
st.markdown("### 上传参考小说 TXT")
uploaded = st.file_uploader("选择 .txt 小说文件", type=["txt"], label_visibility="collapsed")

batch_size = st.slider("每批处理章节数", 10, 50, 20, 5)

if uploaded and st.button("🚀 开始导入", type="primary"):
    # Step 1: 保存文件
    with st.status("正在导入参考小说...", expanded=True) as status_ctx:
        st.write("Step 1/4: 保存上传文件...")
        raw_bytes = uploaded.getvalue()
        enc, confident = detect_encoding(raw_bytes)
        st.write(f"检测到编码：**{enc}** {'(确定)' if confident else '(不确定，使用兜底编码)'}")
        content = raw_bytes.decode(enc)
        with open(sample_path, "w", encoding="utf-8") as f:
            f.write(content)
        st.write(f"已保存到 `{sample_path}`（UTF-8）")

        # Step 2: 拆书
        st.write(f"Step 2/4: 拆书管道（批次大小={batch_size}）...")
        from training.outline_builder import run_outline_build

        with capture_stdout() as buf:
            run_outline_build(txt_path=sample_path, output_dir=ws.reference, batch_size=batch_size)
        show_logs(buf.getvalue())

        # Step 3: 智能分卷
        outlines_dir = os.path.join(ws.reference, "outlines")
        vol_dirs = []
        if os.path.isdir(outlines_dir):
            vol_dirs = [d for d in os.listdir(outlines_dir)
                        if re.match(r'^vol_\d+_.+$', d) and os.path.isdir(os.path.join(outlines_dir, d))]

        if len(vol_dirs) <= 1:
            st.write(f"Step 3/4: 仅 {len(vol_dirs)} 个分卷，执行智能分卷...")
            from training.outline_builder import resegment

            with capture_stdout() as buf:
                resegment(outlines_dir)
            show_logs(buf.getvalue())
        else:
            st.write(f"Step 3/4: 已有 {len(vol_dirs)} 个分卷，跳过智能分卷。")

        # Step 4: 世界观
        st.write("Step 4/4: 提取世界观...")
        from training.adaptive_builder import gen_worldview

        with capture_stdout() as buf:
            gen_worldview(ws)
        show_logs(buf.getvalue())

        status_ctx.update(label="导入完成！", state="complete")

    st.success(f"导入完成！工作区目录：{ws.root}")
    st.rerun()
