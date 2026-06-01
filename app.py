"""harnessNovel Streamlit 可视化界面入口。"""

import os
import sys

# 确保项目根目录在 Python 搜索路径中
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import streamlit as st

st.set_page_config(
    page_title="harnessNovel - AI 网文写作",
    page_icon="📖",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("📖 harnessNovel")
st.markdown("### 长篇网络小说 AI 辅助写作工具")

col1, col2, col3 = st.columns(3)

with col1:
    st.markdown("""
    **核心理念**
    > 先拆书，再仿写 —— 让 AI 深度学习一部优秀作品的精华，再进行有根基的创作。
    """)

with col2:
    st.markdown("""
    **工作流程**
    1. 📥 导入参考小说（拆书）
    2. 📋 生成新小说大纲
    3. 📖 逐卷生成卷纲
    4. 📝 逐章生成章纲
    5. ✍️ 串行撰写正文
    """)

with col3:
    st.markdown("""
    **快速开始**
    1. 前往 **配置管理** 设置 API Key
    2. 前往 **工作区管理** 创建项目
    3. 前往 **导入参考小说** 上传参考书
    4. 按顺序完成各步骤
    """)

st.markdown("---")
st.caption("使用左侧边栏导航到各功能页面。当前工作区和完成状态也会显示在侧边栏中。")
