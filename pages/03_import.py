"""导入参考小说页面。"""

import os
import re
import sys
import time
import queue
import threading

import streamlit as st
from core.workspace import init_workspace
from ui.utils import render_sidebar, workspace_selector, detect_encoding, TeeStdout
from log.logger import get_logger

render_sidebar()
log = get_logger()

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

# ── 初始化 session_state ──
if "import_running" not in st.session_state:
    st.session_state.import_running = False
if "import_complete" not in st.session_state:
    st.session_state.import_complete = False
if "import_error" not in st.session_state:
    st.session_state.import_error = None
if "import_progress" not in st.session_state:
    st.session_state.import_progress = {"pct": 0.0, "status": "", "step": ""}
if "import_logs" not in st.session_state:
    st.session_state.import_logs = []
if "import_stop_event" not in st.session_state:
    st.session_state.import_stop_event = threading.Event()


def _run_import_thread(uploaded_bytes, sample_path, batch_size, ws, stop_event, log_queue):
    """后台线程：执行导入管道。"""
    try:
        # 重定向 stdout 到 TeeStdout
        old_stdout = sys.stdout
        tee = TeeStdout(log_queue)
        sys.stdout = tee

        try:
            from training.outline_builder import run_outline_build, resegment, ImportInterrupted
            from training.adaptive_builder import gen_worldview

            # Step 1: 保存文件
            tee.write("Step 1/4: 保存上传文件...\n")
            enc, confident = detect_encoding(uploaded_bytes)
            tee.write(f"检测到编码：{enc} {'(确定)' if confident else '(不确定)'}\n")
            content = uploaded_bytes.decode(enc)
            with open(sample_path, "w", encoding="utf-8") as f:
                f.write(content)
            tee.write(f"已保存到 {sample_path}（UTF-8）\n")

            if stop_event.is_set():
                raise ImportInterrupted("导入已被用户停止")

            # Step 2: 拆书
            tee.write(f"Step 2/4: 拆书管道（批次大小={batch_size}）...\n")
            run_outline_build(
                txt_path=sample_path,
                output_dir=ws.reference,
                batch_size=batch_size,
                stop_event=stop_event,
            )

            if stop_event.is_set():
                raise ImportInterrupted("导入已被用户停止")

            # Step 3: 智能分卷
            outlines_dir = os.path.join(ws.reference, "outlines")
            vol_dirs = []
            if os.path.isdir(outlines_dir):
                vol_dirs = [d for d in os.listdir(outlines_dir)
                            if re.match(r'^vol_\d+_.+$', d) and os.path.isdir(os.path.join(outlines_dir, d))]

            if len(vol_dirs) <= 1:
                tee.write(f"Step 3/4: 仅 {len(vol_dirs)} 个分卷，执行智能分卷...\n")
                resegment(outlines_dir, stop_event=stop_event)
            else:
                tee.write(f"Step 3/4: 已有 {len(vol_dirs)} 个分卷，跳过智能分卷。\n")

            if stop_event.is_set():
                raise ImportInterrupted("导入已被用户停止")

            # Step 4: 世界观
            tee.write("Step 4/4: 提取世界观...\n")
            gen_worldview(ws, stop_event=stop_event)

            tee.write("\n>>> 导入完成！<<<\n")
            log_queue.put("__DONE__")

        except ImportInterrupted:
            tee.write("\n⚠️ 导入已被用户停止。\n")
            log_queue.put("__STOPPED__")
        finally:
            sys.stdout = old_stdout

    except Exception as e:
        log_queue.put(f"__ERROR__:{str(e)}")


# ── 导入按钮 ──
start_disabled = not uploaded or st.session_state.import_running
if st.button("🚀 开始导入", type="primary", disabled=start_disabled):
    st.session_state.import_running = True
    st.session_state.import_complete = False
    st.session_state.import_error = None
    st.session_state.import_progress = {"pct": 0.0, "status": "准备中...", "step": ""}
    st.session_state.import_logs = []
    st.session_state.import_stop_event.clear()

    log_queue = queue.Queue()
    st.session_state._import_log_queue = log_queue

    thread = threading.Thread(
        target=_run_import_thread,
        args=(uploaded.getvalue(), sample_path, batch_size, ws,
              st.session_state.import_stop_event, log_queue),
        daemon=True,
    )
    thread.start()
    st.session_state._import_thread = thread
    log.info(f"开始导入：{uploaded.name}, 批次大小={batch_size}")
    st.rerun()

# ── 导入进行中：显示进度与实时日志 ──
if st.session_state.import_running:
    log_queue = st.session_state._import_log_queue

    # 收集新日志
    while not log_queue.empty():
        msg = log_queue.get_nowait()
        if msg == "__DONE__":
            st.session_state.import_running = False
            st.session_state.import_complete = True
            st.session_state.import_progress["pct"] = 1.0
            st.session_state.import_progress["status"] = "导入完成！"
            log.success("导入完成")
            break
        elif msg == "__STOPPED__":
            st.session_state.import_running = False
            st.session_state.import_complete = False
            st.session_state.import_progress["status"] = "已停止"
            log.info("导入已被用户停止")
            break
        elif msg.startswith("__ERROR__:"):
            st.session_state.import_running = False
            st.session_state.import_error = msg[len("__ERROR__:"):]
            st.session_state.import_progress["status"] = "导入失败"
            log.error(f"导入失败：{st.session_state.import_error}")
            break
        else:
            st.session_state.import_logs.append(msg)
            # 解析进度信息
            msg_stripped = msg.strip()
            if "Step 1" in msg_stripped:
                st.session_state.import_progress = {"pct": 0.10, "status": "保存文件...", "step": "1/4"}
            elif "Step 2" in msg_stripped:
                st.session_state.import_progress = {"pct": 0.15, "status": "拆书管道...", "step": "2/4"}
            elif "Step 3" in msg_stripped and "跳过" in msg_stripped:
                st.session_state.import_progress = {"pct": 0.70, "status": "跳过智能分卷", "step": "3/4"}
            elif "Step 3" in msg_stripped:
                st.session_state.import_progress = {"pct": 0.70, "status": "智能分卷...", "step": "3/4"}
            elif "Step 4" in msg_stripped:
                st.session_state.import_progress = {"pct": 0.85, "status": "提取世界观...", "step": "4/4"}
            elif "阶段一" in msg_stripped or "提取子纲" in msg_stripped:
                st.session_state.import_progress["status"] = "阶段一：提取批次摘要..."
                st.session_state.import_progress["pct"] = min(0.15 + 0.02, 0.30)
            elif "阶段二" in msg_stripped:
                st.session_state.import_progress["status"] = "阶段二：提取章纲..."
                st.session_state.import_progress["pct"] = max(st.session_state.import_progress["pct"], 0.35)
            elif "阶段三" in msg_stripped or "汇总生成大纲" in msg_stripped:
                st.session_state.import_progress["status"] = "阶段三：汇总大纲..."
                st.session_state.import_progress["pct"] = 0.60
            elif "虚拟分卷" in msg_stripped:
                st.session_state.import_progress["status"] = "虚拟分卷..."
                st.session_state.import_progress["pct"] = 0.65
            elif "提取参考小说世界观" in msg_stripped:
                st.session_state.import_progress["status"] = "提取世界观..."
                st.session_state.import_progress["pct"] = 0.75
            elif "导入完成" in msg_stripped:
                st.session_state.import_progress = {"pct": 1.0, "status": "导入完成！", "step": "✓"}

    # 显示进度条
    pct = st.session_state.import_progress["pct"]
    status_text = st.session_state.import_progress["status"]
    step = st.session_state.import_progress.get("step", "")

    col1, col2 = st.columns([4, 1])
    with col1:
        st.progress(pct, text=f"{step} {status_text}" if step else status_text)

    with col2:
        if st.button("⏹ 停止导入", type="secondary", use_container_width=True):
            st.session_state.import_stop_event.set()
            log.info("用户点击了停止导入按钮")
            st.toast("正在停止导入...")

    # 实时日志显示
    logs = st.session_state.import_logs
    if logs:
        with st.expander("📋 实时日志", expanded=True):
            st.code("".join(logs[-50:]))

    # 自动刷新
    if st.session_state.import_running:
        time.sleep(0.5)
        st.rerun()

# ── 导入完成 ──
if st.session_state.import_complete:
    st.success(f"导入完成！工作区目录：{ws.root}")
    st.balloons()
    st.session_state.import_complete = False

# ── 导入错误 ──
if st.session_state.import_error:
    st.error(f"导入失败：{st.session_state.import_error}")
    st.session_state.import_error = None
