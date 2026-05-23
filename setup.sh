#!/bin/bash
# harnessNovel 一键安装脚本（macOS / Linux）
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# ── 检查 Python 3.9+ ─────────────────────────────────────
PYTHON=""
for cmd in python3 python; do
    if command -v "$cmd" &>/dev/null; then
        ver=$($cmd -c "import sys; print(sys.version_info[:2])" 2>/dev/null | tr -d '(), ')
        if [ "$ver" \> "39" ] 2>/dev/null || [ "$ver" = "39" ]; then
            PYTHON="$cmd"
            break
        fi
    fi
done

if [ -z "$PYTHON" ]; then
    echo "错误：未检测到 Python 3.9+"
    echo ""
    echo "请先安装 Python："
    echo "  macOS:  brew install python3"
    echo "  Ubuntu: sudo apt install python3 python3-venv"
    echo "  或访问 https://www.python.org/downloads/"
    exit 1
fi

echo "检测到 Python: $($PYTHON --version)"

# ── 创建虚拟环境 ─────────────────────────────────────────
if [ ! -d ".venv" ]; then
    echo "正在创建虚拟环境..."
    $PYTHON -m venv .venv
fi

# ── 安装依赖 ─────────────────────────────────────────────
echo "正在安装依赖..."
.venv/bin/pip install --upgrade pip -q
.venv/bin/pip install -e . -q

# ── 注册全局命令 novel ───────────────────────────────────
LINK_PATH=""
for dir in /usr/local/bin "$HOME/.local/bin"; do
    if [ -w "$dir" ] 2>/dev/null; then
        LINK_PATH="$dir/novel"
        break
    fi
done

if [ -n "$LINK_PATH" ]; then
    ln -sf "$SCRIPT_DIR/.venv/bin/novel" "$LINK_PATH"
else
    mkdir -p "$HOME/.local/bin" 2>/dev/null
    if [ -w "$HOME/.local/bin" ]; then
        LINK_PATH="$HOME/.local/bin/novel"
        ln -sf "$SCRIPT_DIR/.venv/bin/novel" "$LINK_PATH"
    else
        echo "需要管理员权限注册全局命令..."
        sudo ln -sf "$SCRIPT_DIR/.venv/bin/novel" /usr/local/bin/novel
        LINK_PATH="/usr/local/bin/novel"
    fi
fi

# 确保 ~/.local/bin 在 PATH 中
if echo "$LINK_PATH" | grep -q "$HOME/.local/bin"; then
    shell_rc="$HOME/.zshrc"
    [ -f "$HOME/.bashrc" ] && shell_rc="$HOME/.bashrc"
    if ! grep -q '.local/bin' "$shell_rc" 2>/dev/null; then
        echo '' >> "$shell_rc"
        echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$shell_rc"
        echo "已将 ~/.local/bin 添加到 $shell_rc"
        export PATH="$HOME/.local/bin:$PATH"
    fi
fi

echo ""
echo "安装完成！全局命令 novel 已注册。"
echo ""
echo "使用方法："
echo "  novel init 我的新小说 --txt 参考小说.txt"
echo ""
echo "首次使用前，请复制配置文件："
echo "  cp .env.example .env"
echo "  然后编辑 .env 填入你的 API Key"
