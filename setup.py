"""
    从 setuptools 导入打包工具setup,find_packages自动找到项目里所有文件夹（包）

    打包 = 把你的整个小说 AI 项目，变成一个【可安装、可分发、可运行】的标准 Python 软件包。
    打包后，你能获得 5 个核心好处
        1. 别人一行命令就能安装你的项目
            没打包前: 别人要下载代码、装依赖、改路径、才能跑。
            打包发布后： 别人只需要： pip install harnessNovel 就能安装好，直接 novel 命令运行。
        2. 安装后直接通过import导入依赖，不用再写 sys.path.insert；Python 会自动识别你的项目目录
        3. 可以直接在终端敲命令运行：novel 就能启动你的 AI 小说写作工具。不用再写：python novel_cli.py
        4. 自动安装所有依赖，通过install_requires配置依赖
        5. 你的项目变成正式软件，可以发布到全世界
"""
from setuptools import setup, find_packages

# 开始配置项目打包信息
setup(
    # 【项目名称】pip 安装/卸载时用的名字
    name="harnessNovel",
    
    # 【版本号】自己定义，更新时修改
    version="0.1.2",
    
    # 【作者名字】
    author="kkddyz",
    
    # 【短描述】一句话说明项目是干嘛的
    description="长篇网络小说写作 AI Agent",
    
    # 【长描述】从 README.md 读取详细介绍（展示在 PyPI 上）
    long_description=open("README.md", encoding="utf-8").read(),
    
    # 告诉系统长描述是 Markdown 格式
    long_description_content_type="text/markdown",
    
    # 项目 GitHub 地址
    url="https://github.com/XTmingyue/harnessNovel",
    
    # 开源协议：GPL-3.0（常用开源协议）
    license="GPL-3.0",
    
    # 【自动发现所有包】
    # 会自动找到 core/ training/ agents/ 等文件夹
    packages=find_packages(),
    
    # 【独立脚本模块】
    # 把根目录的 novel_cli.py 注册成可导入模块
    py_modules=["novel_cli"],
    
    # 【打包时一起包含的资源文件】
    # 把 core/prompts/ 下所有 prompt.txt 一起打包
    package_data={
        "core": ["prompts/*/prompt.txt"],
    },
    
    # 【命令行入口】最关键！
    # 配置后可以直接在终端敲：novel 运行项目
    entry_points={
        "console_scripts": [
            # 命令=模块名:函数名
            # 意思：输入 novel → 运行 novel_cli.py 里的 main()
            "novel=novel_cli:main",
        ],
    },
    
    # 【项目依赖】
    # 安装本项目时，自动安装 openai 库
    install_requires=[
        "openai",
    ],
    
    # 要求 Python 版本 ≥3.9
    python_requires=">=3.9",
)