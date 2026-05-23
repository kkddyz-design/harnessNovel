@echo off
chcp 65001 >nul 2>&1
setlocal enabledelayedexpansion

REM harnessNovel 一键安装脚本（Windows）

cd /d "%~dp0"

REM ── 检查 Python 3.9+ ─────────────────────────────────────
set PYTHON=
for %%c in (python py) do (
    if not defined PYTHON (
        %%c --version >nul 2>&1
        if !errorlevel! equ 0 (
            for /f "tokens=2 delims= " %%v in ('%%c --version 2^>^&1') do (
                for /f "tokens=1,2 delims=." %%a in ("%%v") do (
                    if %%a geq 3 if %%b geq 9 (
                        set PYTHON=%%c
                    )
                )
            )
        )
    )
)

if not defined PYTHON (
    echo 错误：未检测到 Python 3.9+
    echo.
    echo 请先安装 Python：
    echo   winget install Python.Python.3.12
    echo   或访问 https://www.python.org/downloads/
    pause
    exit /b 1
)

for /f "tokens=*" %%v in ('!PYTHON! --version') do echo 检测到 Python: %%v

REM ── 创建虚拟环境 ─────────────────────────────────────────
if not exist ".venv" (
    echo 正在创建虚拟环境...
    !PYTHON! -m venv .venv
    if !errorlevel! neq 0 (
        echo 错误：创建虚拟环境失败
        pause
        exit /b 1
    )
)

REM ── 安装依赖 ─────────────────────────────────────────────
echo 正在安装依赖...
.venv\Scripts\pip.exe install --upgrade pip -q
.venv\Scripts\pip.exe install -e . -q

REM ── 生成 novel.bat 启动脚本 ─────────────────────────────
(
echo @echo off
echo "%~dp0.venv\Scripts\novel.exe" %%*
) > novel.bat

REM ── 注册全局命令 novel ──────────────────────────────────
REM 将项目目录添加到用户 PATH，使 novel.bat 全局可用
set "PROJECT_DIR=%~dp0"
REM 去掉末尾反斜杠
if "%PROJECT_DIR:~-1%"=="\" set "PROJECT_DIR=%PROJECT_DIR:~0,-1%"

REM 检查是否已在 PATH 中
echo %PATH% | findstr /i /c:"%PROJECT_DIR%" >nul
if !errorlevel! neq 0 (
    echo 正在注册全局命令 novel ...
    setx PATH "!PATH!;%PROJECT_DIR%" >nul
    echo 已将项目目录添加到用户 PATH
    echo 请重新打开终端窗口后生效
)

echo.
echo 安装完成！全局命令 novel 已注册。
echo.
echo 使用方法：
echo   novel init 我的新小说 --txt 参考小说.txt
echo.
echo 首次使用前，请复制配置文件：
echo   copy .env.example .env
echo   然后编辑 .env 填入你的 API Key
pause
