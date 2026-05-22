import json
import re


def clean_markdown_symbols(text: str) -> str:
    """清洗文本中的 Markdown 格式符号（加粗、斜体、列表标记等），保留 # 标题。"""
    if not text:
        return text
    # 移除 **加粗** 和 *斜体* 标记（保留内部文字）
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
    text = re.sub(r'\*(.+?)\*', r'\1', text)
    # 移除行首的 - 列表标记（保留内容）
    text = re.sub(r'^(\s*)-\s+', r'\1', text, flags=re.MULTILINE)
    # 移除行首的 > 引用标记
    text = re.sub(r'^>\s*', '', text, flags=re.MULTILINE)
    return text


def normalize_text(text: str) -> str:
    """统一文本格式：去除全角空格缩进、压缩多余空行、去除行尾空白。"""
    if not text:
        return text

    # 去除全角空格（U+3000），中文网文中仅用于段落缩进
    text = text.replace('　', '')

    # 连续3个以上换行压缩为2个（保留段落分隔）
    text = re.sub(r'\n{3,}', '\n\n', text)

    # 每行去除末尾空白
    lines = text.split('\n')
    lines = [line.rstrip() for line in lines]
    text = '\n'.join(lines)

    # 整体去除首尾空白
    text = text.strip()

    return text


def parse_json_response(raw: str) -> dict:
    """清理并解析 LLM 返回的 JSON，处理控制字符、代码块包裹等常见问题。"""
    import re as _re
    cleaned = raw.strip()
    # 去除 markdown 代码块包裹
    if cleaned.startswith("```"):
        first_newline = cleaned.find("\n")
        if first_newline != -1:
            cleaned = cleaned[first_newline + 1:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3].strip()
    # 清除 JSON 值内部的非法控制字符
    cleaned = _re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', cleaned)
    # 修复尾逗号
    cleaned = cleaned.replace(",}", "}").replace(",]", "]")
    return json.loads(cleaned)
