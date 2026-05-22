from setuptools import setup

setup(
    name="harness-novel",
    version="0.1.0",
    py_modules=["novel_cli"],
    entry_points={
        "console_scripts": [
            "novel=novel_cli:main",
        ],
    },
    install_requires=[
        "openai",
    ],
)
