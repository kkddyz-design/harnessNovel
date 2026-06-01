"""章节切分与卷识别模块。将参考小说 TXT 解析为卷列表和章节列表。"""

import sys
import os
import re
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

from core.text_utils import normalize_text

# 独立行且长度合理的卷标题：如 "第一卷 斩落金锁听玄音"
VOLUME_HEADER_RE = re.compile(r'^[ \t　]*第[一二三四五六七八九十百千零0-9]+卷\s+\S+', re.MULTILINE)

# 章节标题：如 "1.第一章 标题"、"第一章 标题"、"第一章（1）标题"、"第一章 (2) 标题"
CHAPTER_HEADER_RE = re.compile(r'^[ \t　]*(\d+\.)?第[一二三四五六七八九十百千零\d]+[章回节](\s*[（(]\d+[）)])?\s*.+', re.MULTILINE)
CHAPTER_HEADER_FALLBACK = re.compile(r'(^[ \t　]*第[一二三四五六七八九十百千零0-9]+[章回节卷].{0,40}?)\n', re.MULTILINE)
VOLUME_TITLE_RE = re.compile(r'^[ \t　]*第[一二三四五六七八九十百千零0-9]+卷\b')

# 卷目录名格式：vol_01_卷名
VOL_DIR_RE = re.compile(r'^vol_(\d+)_(.+)$')


def _read_and_clean(txt_path):
    with open(txt_path, "r", encoding="utf-8") as f:
        lines = f.readlines()
    skip_markers = {"[file content begin]", "[file content end]"}
    return "".join(line for line in lines if line.strip() not in skip_markers)


def _find_volumes(text):
    volumes = []
    for m in VOLUME_HEADER_RE.finditer(text):
        line_start = text.rfind('\n', 0, m.start()) + 1
        line_end = text.find('\n', m.start())
        if line_end == -1:
            line_end = len(text)
        line_text = text[line_start:line_end].strip()
        if len(line_text) > 40 or m.start() != line_start:
            continue
        volumes.append({"title": line_text, "start": m.start()})
    return volumes


def _find_chapters(text):
    matches = list(CHAPTER_HEADER_RE.finditer(text))
    if not matches:
        parts = CHAPTER_HEADER_FALLBACK.split(text)
        chapters = []
        for i in range(1, len(parts), 2):
            title = parts[i].strip()
            body = parts[i + 1].strip() if i + 1 < len(parts) else ""
            content = f"{title}\n{body}"
            if VOLUME_TITLE_RE.match(title):
                continue
            if len(content) < 50:
                continue
            chapters.append({
                "title": title,
                "content": content,
                "pos": text.find(title),
                "volume_idx": -1,
            })
        return chapters

    chapters = []
    for i, match in enumerate(matches):
        start = match.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        content = normalize_text(text[start:end])
        first_newline = content.find('\n')
        title = content[:first_newline].strip() if first_newline != -1 else content[:50]
        if VOLUME_TITLE_RE.match(title):
            continue
        if len(content) < 50:
            continue
        chapters.append({
            "title": title,
            "content": content,
            "pos": start,
            "volume_idx": -1,
        })
    return chapters


def _assign_volumes_by_position(chapters, volumes):
    if not volumes:
        for ch in chapters:
            ch["volume_idx"] = 0
        return

    vol_starts = sorted(v["start"] for v in volumes)
    for ch in chapters:
        pos = ch["pos"]
        assigned = 0
        for vi, vs in enumerate(vol_starts):
            if vs <= pos:
                assigned = vi
            else:
                break
        ch["volume_idx"] = assigned

    for ch in chapters:
        ch.pop("pos", None)


def split_chapters(txt_path):
    """解析参考小说 TXT，返回 (volumes, chapters)。"""
    text = _read_and_clean(txt_path)
    volumes = _find_volumes(text)
    chapters = _find_chapters(text)
    _assign_volumes_by_position(chapters, volumes)
    return volumes, chapters


def group_chapters_by_volume(chapters, volumes):
    """将章节列表按卷分组。"""
    if not volumes:
        return [{"title": "全书", "chapters": chapters}]

    num_volumes = len(volumes)
    groups = []
    for vi in range(num_volumes):
        vol_chapters = [ch for ch in chapters if ch["volume_idx"] == vi]
        if vol_chapters:
            groups.append({"title": volumes[vi]["title"], "chapters": vol_chapters})

    unassigned = [ch for ch in chapters if ch["volume_idx"] < 0 or ch["volume_idx"] >= num_volumes]
    if unassigned:
        if groups:
            groups[-1]["chapters"].extend(unassigned)
        else:
            groups.append({"title": "全书", "chapters": unassigned})

    return groups
