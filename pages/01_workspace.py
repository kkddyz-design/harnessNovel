"""工作区管理页面。"""

import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

import streamlit as st
from core.workspace import list_novels, init_workspace
from ui.utils import render_sidebar, get_workspace_status

st.set_page_config(page_title="工作区管理", page_icon="📌", layout="wide")

ws, status = render_sidebar()

st.title("📌 工作区管理")

# ── 新建工作区 ──
with st.expander("➕ 新建工作区", expanded=not list_novels()):
    new_name = st.text_input("工作区名称", placeholder="我的新小说")
    if st.button("创建", type="primary"):
        if new_name.strip():
            ws_new = init_workspace(new_name.strip())
            st.session_state.active_workspace = new_name.strip()
            st.success(f"工作区「{new_name.strip()}」已创建 → {ws_new.root}")
            st.rerun()
        else:
            st.warning("请输入工作区名称")

st.markdown("---")

# ── 已有工作区列表 ──
novels = list_novels()
if not novels:
    st.info("暂无工作区，请在上方创建一个。")
else:
    st.markdown(f"### 已有工作区（共 {len(novels)} 个）")

    for name in novels:
        w = init_workspace(name)
        s = get_workspace_status(w)

        done = sum(1 for v in s.values() if v)
        total = len(s)
        pct = int(done / total * 100)

        is_active = st.session_state.get("active_workspace") == name

        cols = st.columns([3, 1, 1, 1])
        with cols[0]:
            prefix = "⭐ " if is_active else ""
            st.markdown(f"**{prefix}{name}**")
            st.caption(w.root)
        with cols[1]:
            st.metric("完成度", f"{done}/{total}")
        with cols[2]:
            st.progress(pct / 100, text=f"{pct}%")
        with cols[3]:
            if not is_active:
                if st.button("设为活跃", key=f"set_{name}"):
                    st.session_state.active_workspace = name
                    st.rerun()
            else:
                st.success("当前")

        st.markdown("---")
