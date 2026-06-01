import sys
import os
import re
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
import argparse
import json
import shutil

from core.llm_provider import LLMProvider
from core.prompt_loader import PromptLoader
from core.config import ConfigLoader
from core.text_utils import normalize_text, read_file, write_file
from core.workspace import NovelWorkspace, init_workspace
from log.logger import get_logger
from training.splitter import (
    VOL_DIR_RE, split_chapters, group_chapters_by_volume,
)

log = get_logger()


def _vol_dir_name(vol_idx, title):
    """生成卷目录名，如 vol_01_斩落金锁听玄音。"""
    safe = re.sub(r'[\\/:*?"<>|\s]', '_', title)[:30]
    return f"vol_{vol_idx + 1:02d}_{safe}"


def _batch_file_name(batch_start, batch_end):
    return f"batch_{batch_start + 1:03d}_{batch_end:03d}.md"



def extract_volume_outline(vol_idx, volume_title, chapters, llm, outlines_dir, batch_size=20, stop_event=None):
    """提取单卷卷纲。每批结果立即存盘，支持断点续传。"""
    vol_dir = os.path.join(outlines_dir, _vol_dir_name(vol_idx, volume_title))
    total = len(chapters)
    log.info(f"    [{volume_title}] 共 {total} 章")

    # 1. 分批提取子纲，每批存盘
    batch_files = []
    for batch_start in range(0, total, batch_size):
        _check_stop(stop_event)
        batch_end = min(batch_start + batch_size, total)
        batch = chapters[batch_start:batch_end]
        bfile = os.path.join(vol_dir, _batch_file_name(batch_start, batch_end))

        # 断点续传：已有文件则跳过
        existing = read_file(bfile)
        if existing:
            log.info(f"    -> 第 {batch_start+1}-{batch_end} 章子纲已存在，跳过。")
            batch_files.append(bfile)
            continue

        log.info(f"    -> 提取子纲（第 {batch_start+1}-{batch_end} 章，共 {len(batch)} 章）...")
        chapters_text = "\n\n".join(ch["content"] for ch in batch)
        prompt = PromptLoader.load(
            "batch_extract",
            start_chapter=batch_start + 1,
            end_chapter=batch_end,
            chapters_text=chapters_text
        )
        result = normalize_text(llm.generate(prompt))
        write_file(bfile, result)
        log.info(f"    -> 子纲已保存：{bfile}")
        batch_files.append(bfile)

    # 2. 合并子纲为卷纲
    vol_outline_path = os.path.join(vol_dir, "volume_outline.md")
    existing_outline = read_file(vol_outline_path)
    if existing_outline:
        log.info(f"    -> 卷纲已存在，跳过合并。")
        return existing_outline

    # 读取所有子纲文件（不占用累积内存，逐文件读取）
    batch_summaries = []
    for bf in batch_files:
        content = read_file(bf)
        if content:
            batch_summaries.append(content)

    if len(batch_summaries) <= 1:
        # 只有一批，直接作为卷纲
        outline = batch_summaries[0] if batch_summaries else ""
        write_file(vol_outline_path, outline)
        log.info(f"    -> 卷纲已保存：{vol_outline_path}")
        return outline

    # 多批合并
    log.info(f"    -> 合并 {len(batch_summaries)} 段子纲为卷纲...")
    all_subs = "\n\n---\n\n".join(batch_summaries)
    merge_prompt = PromptLoader.load(
        "volume_merge",
        volume_title=volume_title,
        start_chapter=1,
        end_chapter=total,
        total_chapters=total,
        total_batches=len(batch_summaries),
        batch_summaries=all_subs
    )
    merged = normalize_text(llm.generate(merge_prompt))
    write_file(vol_outline_path, merged)
    log.info(f"    -> 卷纲已保存：{vol_outline_path}")
    return merged


def extract_novel_outline(volume_outlines, llm, outlines_dir):
    """汇总所有卷纲，生成完整大纲。"""
    novel_outline_path = os.path.join(outlines_dir, "novel_outline.md")
    existing = read_file(novel_outline_path)
    if existing:
        log.info(f"  -> 完整大纲已存在，跳过。")
        return existing

    log.info(f"  -> 汇总 {len(volume_outlines)} 卷卷纲，生成完整大纲...")
    all_outlines = "\n\n---\n\n".join(
        f"【{vo['title']}】\n{vo['outline']}"
        for vo in volume_outlines
    )
    prompt = PromptLoader.load("novel_extract", all_volume_outlines=all_outlines)
    novel_outline = normalize_text(llm.generate(prompt))
    write_file(novel_outline_path, novel_outline)
    log.info(f"  -> 完整大纲已保存：{novel_outline_path}")
    return novel_outline


def _parse_virtual_volumes(llm_result):
    """解析 LLM 虚拟分卷输出为 [(vol_idx, title, start_ch, end_ch), ...]。"""
    volumes = []
    for line in llm_result.strip().split('\n'):
        line = line.strip()
        m = re.match(r'卷(\d+)：(.+?)\s*\|\s*第(\d+)-(\d+)章', line)
        if m:
            vol_idx = int(m.group(1))
            title = m.group(2).strip()
            start_ch = int(m.group(3))
            end_ch = int(m.group(4))
            volumes.append((vol_idx, title, start_ch, end_ch))
    return volumes


def _extract_segment_endpoints(batch_dir):
    """从批次摘要文件中提取所有故事片段的结束章节号。返回排序后的端点列表。"""
    endpoints = set()
    for bf in sorted(os.listdir(batch_dir)):
        if not re.match(r'^batch_\d+_\d+\.md$', bf):
            continue
        content = read_file(os.path.join(batch_dir, bf))
        if not content:
            continue
        for m in re.finditer(r'[【]?片段\d+[：:]\s*第(\d+)-(\d+)章', content):
            endpoints.add(int(m.group(2)))
    return sorted(endpoints)


def _snap_to_segments(virtual_volumes, segment_endpoints, total_chapters):
    """将虚拟卷的章节边界对齐到最近的片段端点，确保不拆碎片段。"""
    if not segment_endpoints:
        return virtual_volumes

    snapped = []
    for i, (vi, title, start_ch, end_ch) in enumerate(virtual_volumes):
        # 第一卷的起始章节保持 1
        s = 1 if i == 0 else snapped[-1][3] + 1
        # 结束章节对齐到最近的片段端点（不超过自身太多）
        candidates = [ep for ep in segment_endpoints if ep >= s]
        if candidates:
            # 找最近的端点，偏向不超过原值太多
            nearest = min(candidates, key=lambda x: abs(x - end_ch))
            e = nearest
        else:
            e = end_ch
        snapped.append((vi, title, s, e))
    return snapped


def _assign_batches_to_volumes(src_dir, virtual_volumes):
    """将批次文件分配给覆盖比例最大的虚拟卷，避免同一批次出现在多个卷中。

    Returns:
        dict: {vol_dir: [batch_file_name, ...]}
    """
    # 收集所有批次文件信息
    batches = []
    for bf in sorted(os.listdir(src_dir)):
        m = re.match(r'^batch_(\d+)_(\d+)\.md$', bf)
        if not m:
            continue
        batches.append((bf, int(m.group(1)), int(m.group(2))))

    assignment = {i: [] for i in range(len(virtual_volumes))}

    for bf, b_start, b_end in batches:
        best_vol = -1
        best_overlap = 0
        for i, (vi, title, start_ch, end_ch) in enumerate(virtual_volumes):
            overlap_start = max(b_start, start_ch)
            overlap_end = min(b_end, end_ch)
            overlap = max(0, overlap_end - overlap_start + 1)
            if overlap > best_overlap:
                best_overlap = overlap
                best_vol = i
        if best_vol >= 0:
            assignment[best_vol].append(bf)

    return assignment


def _copy_chapter_outlines_for_volume(src_dir, dst_dir, start_ch, end_ch):
    """从 src_dir/chapter_outlines/ 复制 [start_ch, end_ch] 范围的章纲到 dst_dir/chapter_outlines/。"""
    src_ch_dir = os.path.join(src_dir, "chapter_outlines")
    dst_ch_dir = os.path.join(dst_dir, "chapter_outlines")
    if not os.path.isdir(src_ch_dir):
        return
    os.makedirs(dst_ch_dir, exist_ok=True)
    for ch_num in range(start_ch, end_ch + 1):
        src_file = os.path.join(src_ch_dir, f"chapter_{ch_num:03d}.md")
        if os.path.exists(src_file):
            shutil.copy2(src_file, os.path.join(dst_ch_dir, f"chapter_{ch_num:03d}.md"))


def _generate_virtual_volume_outline(vol_dir, start_ch, end_ch, llm):
    """读取虚拟卷覆盖的批次摘要，调用 LLM 生成卷纲。"""
    vol_outline_path = os.path.join(vol_dir, "volume_outline.md")
    existing = read_file(vol_outline_path)
    if existing:
        return existing

    batch_summaries = []
    for bf in sorted(os.listdir(vol_dir)):
        m = re.match(r'^batch_\d+_\d+\.md$', bf)
        if not m:
            continue
        content = read_file(os.path.join(vol_dir, bf))
        if content:
            batch_summaries.append(content)

    if not batch_summaries:
        return ""

    if len(batch_summaries) == 1:
        outline = batch_summaries[0]
    else:
        all_subs = "\n\n---\n\n".join(batch_summaries)
        total = end_ch - start_ch + 1
        merge_prompt = PromptLoader.load(
            "volume_merge",
            volume_title="虚拟卷",
            start_chapter=start_ch,
            end_chapter=end_ch,
            total_chapters=total,
            total_batches=len(batch_summaries),
            batch_summaries=all_subs,
        )
        outline = normalize_text(llm.generate(merge_prompt))

    write_file(vol_outline_path, outline)
    return outline


def _extract_segment_ranges(batch_dir):
    """从批次摘要中提取故事片段的章节范围。返回 [(start_ch, end_ch), ...]。"""
    segments = []
    for bf in sorted(os.listdir(batch_dir)):
        if not re.match(r'^batch_\d+_\d+\.md$', bf):
            continue
        content = read_file(os.path.join(batch_dir, bf))
        if not content:
            continue
        for m in re.finditer(r'[【]?片段\d+[：:]\s*第(\d+)-(\d+)章', content):
            segments.append((int(m.group(1)), int(m.group(2))))
    return segments


def _parse_batch_chapter_outlines(result):
    """解析多章章纲的 LLM 输出，返回 {chapter_num: outline_text}。"""
    outlines = {}
    parts = re.split(r'[【]?第(\d+)章\s*章纲[】]?', result)
    for i in range(1, len(parts) - 1, 2):
        ch_num = int(parts[i])
        content = parts[i + 1].strip() if i + 1 < len(parts) else ""
        if content:
            outlines[ch_num] = content
    return outlines


def _generate_chapter_outlines_batch(chapters_batch, llm):
    """批量生成多章章纲。chapters_batch: [(global_ch_num, chapter_dict), ...]。
    返回与输入顺序对应的 {global_ch_num: outline_text}，不依赖 LLM 返回的编号。
    """
    chapters_text_parts = []
    for ch_num, ch in chapters_batch:
        chapters_text_parts.append(f"=== 第{ch_num}章 ===\n{ch['content']}")
    chapters_text = "\n\n".join(chapters_text_parts)

    prompt = PromptLoader.load("chapter_outline_extract", chapters_text=chapters_text)
    result = normalize_text(llm.generate(prompt))
    parsed = _parse_batch_chapter_outlines(result)

    # 按输入顺序匹配：先尝试精确匹配编号，再按顺序兜底
    outlines = {}
    used_indices = set()
    # 第一轮：精确匹配
    for i, (ch_num, _) in enumerate(chapters_batch):
        if ch_num in parsed and i not in used_indices:
            outlines[ch_num] = parsed[ch_num]
            used_indices.add(i)
    # 第二轮：未匹配的输入按顺序取未使用的解析结果
    parsed_values = [v for k, v in sorted(parsed.items()) if k not in outlines]
    pi = 0
    for i, (ch_num, _) in enumerate(chapters_batch):
        if i not in used_indices and pi < len(parsed_values):
            outlines[ch_num] = parsed_values[pi]
            pi += 1

    return outlines


def _load_existing_volumes(outlines_dir, groups, chapters):
    """检查是否已有完整的批次摘要和卷纲。如果有，返回 {volume_outlines, groups}；否则返回 None。

    支持两种情况：
    1. 自然卷：vol_XX_<title>/ 下有 batch 文件和 volume_outline.md
    2. 虚拟卷：vol_XX_<title>/ 下有 meta.json、batch 文件和 volume_outline.md
    """
    if not os.path.isdir(outlines_dir):
        return None

    # 扫描已有的卷目录
    vol_dirs = []
    for name in sorted(os.listdir(outlines_dir)):
        if VOL_DIR_RE.match(name):
            vol_path = os.path.join(outlines_dir, name)
            if os.path.isdir(vol_path):
                vol_dirs.append((name, vol_path))

    if not vol_dirs:
        return None

    # 检查每个卷目录是否有完整的批次文件和卷纲
    volume_outlines = []
    vol_groups = []
    all_complete = True

    for name, vol_path in vol_dirs:
        m = VOL_DIR_RE.match(name)
        vol_idx = int(m.group(1))
        title = m.group(2).replace('_', ' ')

        # 检查卷纲
        vol_outline = read_file(os.path.join(vol_path, "volume_outline.md"))
        if not vol_outline:
            all_complete = False
            break

        # 检查批次文件
        batch_files = [f for f in os.listdir(vol_path) if re.match(r'^batch_\d+_\d+\.md$', f)]
        if not batch_files:
            all_complete = False
            break

        volume_outlines.append({"title": title, "outline": vol_outline})

        # 根据是否有 meta.json 判断是虚拟卷还是自然卷
        meta = None
        meta_path = os.path.join(vol_path, "meta.json")
        if os.path.exists(meta_path):
            with open(meta_path, "r", encoding="utf-8") as f:
                meta = json.load(f)

        if meta:
            # 虚拟卷：从 meta.json 获取章节范围
            start_ch = meta["start_ch"]
            end_ch = meta["end_ch"]
            vol_chapters = [chapters[i] for i in range(len(chapters))
                            if start_ch <= (i + 1) <= end_ch]
        else:
            # 自然卷：按卷索引分组
            vol_chapters = [ch for ch in chapters if ch.get("volume_idx", -1) == vol_idx - 1]

        vol_groups.append({"title": title, "chapters": vol_chapters})

    if not all_complete:
        return None

    return {"volume_outlines": volume_outlines, "groups": vol_groups}


class ImportInterrupted(Exception):
    """导入被用户中断。"""
    pass


def _check_stop(stop_event):
    if stop_event and stop_event.is_set():
        raise ImportInterrupted("导入已被用户停止")


def run_outline_build(txt_path=None, output_dir=None, batch_size=20, skip_chapter_outlines=False, stop_event=None):
    if txt_path is None:
        txt_path = os.path.join(DATA_DIR, "sample_novel.txt")
    if output_dir is None:
        output_dir = DATA_DIR

    if not os.path.exists(txt_path):
        log.info(f"错误：未找到小说文件 {txt_path}")
        return

    outlines_dir = os.path.join(output_dir, "outlines")

    log.info(f">>> 参考小说大纲梳理启动 <<<")
    log.info(f"读取文件：{txt_path}")
    log.info(f"输出目录：{outlines_dir}")

    # 1. 切分章节并识别卷
    volumes, chapters = split_chapters(txt_path)
    log.info(f"解析出 {len(volumes)} 卷，{len(chapters)} 章，每批 {batch_size} 章。")
    _check_stop(stop_event)

    # 2. 按卷分组
    groups = group_chapters_by_volume(chapters, volumes)
    for g in groups:
        n = len(g['chapters'])
        batches = (n + batch_size - 1) // batch_size
        log.info(f"  {g['title']}：{n} 章 -> {batches} 批")

    # 3. 检查是否已有完整的批次摘要和卷纲（跳过阶段一）
    existing_volumes = _load_existing_volumes(outlines_dir, groups, chapters)

    # 4. 初始化 LLM
    builder_config = ConfigLoader.get_data_builder_config()
    if not builder_config.get("api_key"):
        builder_config["api_key"] = os.getenv("OPENAI_API_KEY")
    if not builder_config.get("api_key"):
        log.info("错误：未检测到 API Key。")
        return
    llm = LLMProvider(**builder_config)
    _check_stop(stop_event)

    if existing_volumes:
        # 已有完整数据，跳过阶段一和虚拟分卷
        log.info(f"\n--- 阶段一：已跳过（检测到已有批次摘要和卷纲） ---")
        volume_outlines = existing_volumes["volume_outlines"]
        groups = existing_volumes["groups"]
    else:
        # 4. 按卷提取批次摘要和卷纲（增量保存）
        log.info(f"\n--- 阶段一：按卷提取批次摘要和卷纲 ---")
        volume_outlines = []
        for vi, g in enumerate(groups):
            _check_stop(stop_event)
            log.info(f"\n  处理：{g['title']}")
            outline = extract_volume_outline(vi, g["title"], g["chapters"], llm, outlines_dir, batch_size, stop_event=stop_event)
            volume_outlines.append({"title": g["title"], "outline": outline})

    # 汇总卷纲文件
    volume_outline_path = os.path.join(outlines_dir, "volume_outline.md")
    with open(volume_outline_path, "w", encoding="utf-8") as f:
        f.write("# 参考小说卷纲\n\n")
        for vo in volume_outlines:
            f.write(f"## {vo['title']}\n\n{vo['outline']}\n\n---\n\n")
    log.info(f"\n卷纲汇总已保存至：{volume_outline_path}")

    # 汇总生成完整大纲
    extract_novel_outline(volume_outlines, llm, outlines_dir)

def resegment(outlines_dir, stop_event=None):
    """基于已有批次摘要重新执行虚拟分卷。

    两种情况：
    1. vol_01_全书/ 存在：直接从此目录重新分卷。
    2. 已有虚拟卷目录（含 meta.json）：将所有卷的批次摘要汇总到 vol_01_全书/ 并去重，再重新分卷。
    """
    all_batch_dir = None
    for name in os.listdir(outlines_dir):
        if VOL_DIR_RE.match(name) and "全书" in name:
            all_batch_dir = os.path.join(outlines_dir, name)
            break

    if not all_batch_dir or not os.path.isdir(all_batch_dir):
        # 没有全书目录，查找虚拟卷目录并汇总批次摘要
        vol_dirs = []
        for name in sorted(os.listdir(outlines_dir)):
            vol_path = os.path.join(outlines_dir, name)
            if os.path.isdir(vol_path) and VOL_DIR_RE.match(name):
                vol_dirs.append((name, vol_path))

        if not vol_dirs:
            log.info("错误：未找到任何卷目录，无法执行重新分卷。")
            return

        log.info("  -> 未找到 vol_01_全书，从现有虚拟卷汇总批次摘要...")
        all_batch_dir = os.path.join(outlines_dir, _vol_dir_name(0, "全书"))
        os.makedirs(all_batch_dir, exist_ok=True)

        # 收集所有批次文件并按文件名去重（同名文件只保留一份）
        seen = set()
        for name, vol_path in vol_dirs:
            for bf in sorted(os.listdir(vol_path)):
                if re.match(r'^batch_\d+_\d+\.md$', bf) and bf not in seen:
                    shutil.copy2(os.path.join(vol_path, bf), os.path.join(all_batch_dir, bf))
                    seen.add(bf)

        # 删除旧的虚拟卷目录
        for name, vol_path in vol_dirs:
            shutil.rmtree(vol_path, ignore_errors=True)
            log.info(f"  -> 已删除旧卷目录：{name}")

        log.info(f"  -> 已汇总 {len(seen)} 个批次摘要到 vol_01_全书/")

    # 以下统一处理：从 all_batch_dir 读取批次摘要并重新分卷
    batch_summaries = []
    for bf in sorted(os.listdir(all_batch_dir)):
        if re.match(r'^batch_\d+_\d+\.md$', bf):
            content = read_file(os.path.join(all_batch_dir, bf))
            if content:
                batch_summaries.append(content)

    if not batch_summaries:
        log.info("错误：未找到批次摘要。")
        return

    # 初始化 LLM
    builder_config = ConfigLoader.get_data_builder_config()
    if not builder_config.get("api_key"):
        builder_config["api_key"] = os.getenv("OPENAI_API_KEY")
    if not builder_config.get("api_key"):
        log.info("错误：未检测到 API Key。")
        return
    llm = LLMProvider(**builder_config)

    # 推算总章数
    total_ch = 0
    for bf in sorted(os.listdir(all_batch_dir)):
        m = re.match(r'^batch_\d+_(\d+)\.md$', bf)
        if m:
            total_ch = max(total_ch, int(m.group(1)))

    log.info(f">>> 虚拟分卷（重新分卷）<<<")
    log.info(f"  批次摘要：{len(batch_summaries)} 个文件，约 {total_ch} 章")
    _check_stop(stop_event)

    all_batches_text = "\n\n---\n\n".join(batch_summaries)
    log.info(f"  -> 调用 LLM 分析批次摘要，识别卷边界...")
    seg_prompt = PromptLoader.load("virtual_volume_segment", batch_summaries=all_batches_text)
    seg_result = normalize_text(llm.generate(seg_prompt))
    _check_stop(stop_event)

    virtual_volumes = _parse_virtual_volumes(seg_result)
    if not virtual_volumes:
        log.info("  警告：LLM 未输出有效分卷结果，保持原状。")
        return

    # 将边界对齐到故事片段端点
    segment_endpoints = _extract_segment_endpoints(all_batch_dir)
    virtual_volumes = _snap_to_segments(virtual_volumes, segment_endpoints, total_ch)

    # 检查每卷章节数是否 >= 60，不满足则合并到相邻卷
    virtual_volumes = _ensure_min_chapters(virtual_volumes, min_chapters=60)

    # 确保覆盖全部章节：首卷从1开始，末卷到 total_ch 结束
    virtual_volumes = _ensure_full_coverage(virtual_volumes, total_ch)

    log.info(f"  -> 识别出 {len(virtual_volumes)} 卷（已对齐片段边界）：")
    for vi, title, sc, ec in virtual_volumes:
        log.info(f"     卷{vi}：{title}（第{sc}-{ec}章，{ec - sc + 1}章）")
    covered = sum(ec - sc + 1 for _, _, sc, ec in virtual_volumes)
    log.info(f"  -> 覆盖：{covered}/{total_ch} 章")

    # 分配批次文件
    batch_assignment = _assign_batches_to_volumes(all_batch_dir, virtual_volumes)

    # 为每个虚拟卷创建目录、复制文件、生成卷纲
    new_volume_outlines = []
    for i, (vi, vol_title, start_ch, end_ch) in enumerate(virtual_volumes):
        _check_stop(stop_event)
        vol_dir_name = _vol_dir_name(vi - 1, vol_title)
        vol_dir = os.path.join(outlines_dir, vol_dir_name)

        log.info(f"  -> 组织卷{vi}（{vol_title}，第{start_ch}-{end_ch}章）...")
        os.makedirs(vol_dir, exist_ok=True)
        for bf in batch_assignment.get(i, []):
            shutil.copy2(os.path.join(all_batch_dir, bf), os.path.join(vol_dir, bf))

        meta = {"start_ch": start_ch, "end_ch": end_ch}
        with open(os.path.join(vol_dir, "meta.json"), "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False)

        outline = _generate_virtual_volume_outline(vol_dir, start_ch, end_ch, llm)
        new_volume_outlines.append({"title": vol_title, "outline": outline})
        log.info(f"     卷纲已生成")

    # 删除原始"全书"伪卷目录
    shutil.rmtree(all_batch_dir, ignore_errors=True)

    # 重写汇总卷纲文件
    volume_outline_path = os.path.join(outlines_dir, "volume_outline.md")
    with open(volume_outline_path, "w", encoding="utf-8") as f:
        f.write("# 参考小说卷纲\n\n")
        for vo in new_volume_outlines:
            f.write(f"## {vo['title']}\n\n{vo['outline']}\n\n---\n\n")

    # 重新生成大纲
    log.info(f"\n  -> 重新汇总生成大纲...")
    extract_novel_outline(new_volume_outlines, llm, outlines_dir)

    log.info(f"\n>>> 虚拟分卷完成 <<<")
    log.info(f"  卷纲汇总：{volume_outline_path}")

def _ensure_full_coverage(virtual_volumes, total_ch):
    """确保虚拟卷覆盖全部章节范围：首卷从1开始，末卷到 total_ch 结束，中间无间隙。"""
    if not virtual_volumes:
        return virtual_volumes

    result = []
    for i, (vi, title, start_ch, end_ch) in enumerate(virtual_volumes):
        s = 1 if i == 0 else (result[-1][3] + 1)
        # 最后一卷确保延伸到 total_ch
        if i == len(virtual_volumes) - 1:
            e = max(end_ch, total_ch)
        else:
            e = end_ch
        result.append((vi, title, s, e))
    return result


def _ensure_min_chapters(virtual_volumes, min_chapters=60):
    """合并章节数不足 min_chapters 的虚拟卷到相邻卷。"""
    if not virtual_volumes:
        return virtual_volumes

    result = list(virtual_volumes)
    changed = True
    while changed:
        changed = False
        new_result = []
        i = 0
        while i < len(result):
            vi, title, start_ch, end_ch = result[i]
            ch_count = end_ch - start_ch + 1
            if ch_count < min_chapters:
                # 尝试合并到下一卷
                if i + 1 < len(result):
                    nvi, ntitle, ns, ne = result[i + 1]
                    merged = (nvi, ntitle, start_ch, ne)
                    new_result.append(merged)
                    log.info(f"  -> 卷{vi}（{ch_count}章）不足{min_chapters}章，合并到卷{nvi}")
                    i += 2
                    changed = True
                # 尝试合并到前一卷
                elif new_result:
                    pvi, ptitle, ps, pe = new_result[-1]
                    new_result[-1] = (pvi, ptitle, ps, end_ch)
                    log.info(f"  -> 卷{vi}（{ch_count}章）不足{min_chapters}章，合并到卷{pvi}")
                    i += 1
                    changed = True
                else:
                    new_result.append(result[i])
                    i += 1
            else:
                new_result.append(result[i])
                i += 1
        result = new_result

    # 重新编号
    final = []
    for idx, (vi, title, start_ch, end_ch) in enumerate(result):
        final.append((idx + 1, title, start_ch, end_ch))
    return final


    # 4.5 虚拟分卷：如果只有"全书"伪卷，自动划分为虚拟卷
    need_virtual = len(groups) == 1 and groups[0]["title"] == "全书"
    if need_virtual:
        _check_stop(stop_event)
        log.info(f"\n--- 虚拟分卷：全书无自然分卷，自动识别卷边界 ---")
        all_batch_dir = os.path.join(outlines_dir, _vol_dir_name(0, "全书"))

        # 读取所有批次摘要
        batch_summaries = []
        for bf in sorted(os.listdir(all_batch_dir)):
            if re.match(r'^batch_\d+_\d+\.md$', bf):
                content = read_file(os.path.join(all_batch_dir, bf))
                if content:
                    batch_summaries.append(content)

        if not batch_summaries:
            log.info("  错误：未找到批次摘要，跳过虚拟分卷。")
        else:
            all_batches_text = "\n\n---\n\n".join(batch_summaries)
            log.info(f"  -> 调用 LLM 分析 {len(batch_summaries)} 个批次摘要，识别卷边界...")
            _check_stop(stop_event)
            seg_prompt = PromptLoader.load("virtual_volume_segment", batch_summaries=all_batches_text)
            seg_result = normalize_text(llm.generate(seg_prompt))
            _check_stop(stop_event)

            virtual_volumes = _parse_virtual_volumes(seg_result)
            if not virtual_volumes:
                log.info("  警告：LLM 未输出有效分卷结果，保持原状。")
            else:
                # 将边界对齐到故事片段端点
                segment_endpoints = _extract_segment_endpoints(all_batch_dir)
                total_ch = len(groups[0]["chapters"])
                virtual_volumes = _snap_to_segments(virtual_volumes, segment_endpoints, total_ch)
                virtual_volumes = _ensure_full_coverage(virtual_volumes, total_ch)

                log.info(f"  -> 识别出 {len(virtual_volumes)} 卷（已对齐片段边界）：")
                for vi, title, sc, ec in virtual_volumes:
                    log.info(f"     卷{vi}：{title}（第{sc}-{ec}章，{ec - sc + 1}章）")
                covered = sum(ec - sc + 1 for _, _, sc, ec in virtual_volumes)
                log.info(f"  -> 覆盖：{covered}/{total_ch} 章")

                # 为每个虚拟卷创建目录、复制文件、生成卷纲
                batch_assignment = _assign_batches_to_volumes(all_batch_dir, virtual_volumes)
                new_volume_outlines = []
                for i, (vi, vol_title, start_ch, end_ch) in enumerate(virtual_volumes):
                    vol_dir_name = _vol_dir_name(vi - 1, vol_title)
                    vol_dir = os.path.join(outlines_dir, vol_dir_name)

                    log.info(f"  -> 组织卷{vi}（{vol_title}，第{start_ch}-{end_ch}章）...")
                    os.makedirs(vol_dir, exist_ok=True)
                    for bf in batch_assignment.get(i, []):
                        shutil.copy2(os.path.join(all_batch_dir, bf), os.path.join(vol_dir, bf))

                    # 写入虚拟卷元数据，供 reference_finder 使用
                    meta = {"start_ch": start_ch, "end_ch": end_ch}
                    with open(os.path.join(vol_dir, "meta.json"), "w", encoding="utf-8") as f:
                        json.dump(meta, f, ensure_ascii=False)

                    outline = _generate_virtual_volume_outline(vol_dir, start_ch, end_ch, llm)
                    new_volume_outlines.append({"title": vol_title, "outline": outline})
                    log.info(f"     卷纲已生成")

                # 删除原始"全书"伪卷目录
                shutil.rmtree(all_batch_dir, ignore_errors=True)

                # 重建 groups 和 volume_outlines
                volume_outlines = new_volume_outlines
                new_groups = []
                all_chapters = groups[0]["chapters"]
                for vi, vol_title, start_ch, end_ch in virtual_volumes:
                    vol_chapters = [all_chapters[i] for i in range(len(all_chapters))
                                    if start_ch <= (i + 1) <= end_ch]
                    new_groups.append({"title": vol_title, "chapters": vol_chapters})
                groups = new_groups

                # 重写汇总卷纲文件
                with open(volume_outline_path, "w", encoding="utf-8") as f:
                    f.write("# 参考小说卷纲\n\n")
                    for vo in volume_outlines:
                        f.write(f"## {vo['title']}\n\n{vo['outline']}\n\n---\n\n")
                log.info(f"  -> 虚拟分卷完成，卷纲已更新")

    # 5. 按卷提取每章章纲（按故事片段分批，每批最多5章）
    if not skip_chapter_outlines:
        _check_stop(stop_event)
        MAX_CHAPTERS_PER_BATCH = 5
        log.info(f"\n--- 阶段二：提取每章章纲（按片段分批） ---")
        for vi, g in enumerate(groups):
            _check_stop(stop_event)
            vol_dir = os.path.join(outlines_dir, _vol_dir_name(vi, g["title"]))
            ch_outlines_dir = os.path.join(vol_dir, "chapter_outlines")
            os.makedirs(ch_outlines_dir, exist_ok=True)
            log.info(f"\n  {g['title']}：{len(g['chapters'])} 章")

            # 从批次摘要中提取片段范围
            segment_ranges = _extract_segment_ranges(vol_dir)

            # 检测是否为虚拟卷，获取章节偏移量
            meta_path = os.path.join(vol_dir, "meta.json")
            vol_offset = 0
            if os.path.exists(meta_path):
                with open(meta_path, "r", encoding="utf-8") as f:
                    meta = json.load(f)
                vol_offset = meta["start_ch"] - 1

            if segment_ranges:
                # 按片段分批
                for seg_start, seg_end in segment_ranges:
                    # 收集本片段中尚未生成章纲的章节
                    seg_chapters = []
                    for ci, ch in enumerate(g["chapters"]):
                        global_ch = ci + 1 + vol_offset
                        local_ch = ci + 1
                        if seg_start <= global_ch <= seg_end:
                            ch_file = os.path.join(ch_outlines_dir, f"chapter_{local_ch:03d}.md")
                            if not read_file(ch_file):
                                seg_chapters.append((global_ch, ch))

                    if not seg_chapters:
                        continue

                    # 按 MAX_CHAPTERS_PER_BATCH 切分
                    for bi in range(0, len(seg_chapters), MAX_CHAPTERS_PER_BATCH):
                        _check_stop(stop_event)
                        batch = seg_chapters[bi:bi + MAX_CHAPTERS_PER_BATCH]
                        ch_range = f"{batch[0][0]}-{batch[-1][0]}"
                        log.info(f"    -> 批量提取第{ch_range}章章纲（{len(batch)}章）...")
                        outlines = _generate_chapter_outlines_batch(batch, llm)
                        for ch_num, outline in outlines.items():
                            local_num = ch_num - vol_offset
                            ch_file = os.path.join(ch_outlines_dir, f"chapter_{local_num:03d}.md")
                            write_file(ch_file, outline)
                        # 处理 LLM 未返回的章节
                        for ch_num, ch in batch:
                            local_num = ch_num - vol_offset
                            ch_file = os.path.join(ch_outlines_dir, f"chapter_{local_num:03d}.md")
                            if not read_file(ch_file):
                                log.info(f"    -> 第{ch_num}章未在批量结果中，单独生成...")
                                prompt = PromptLoader.load(
                                    "chapter_outline_extract",
                                    chapters_text=f"=== 第{ch_num}章 ===\n{ch['content']}",
                                )
                                result = normalize_text(llm.generate(prompt))
                                write_file(ch_file, result)
                        saved_count = sum(1 for cn, _ in batch if read_file(os.path.join(ch_outlines_dir, f"chapter_{cn - vol_offset:03d}.md")))
                        log.info(f"    -> 第{ch_range}章章纲已保存（{saved_count}/{len(batch)}）")
            else:
                # 无片段信息时，按固定批次切分
                pending = []
                for ci, ch in enumerate(g["chapters"]):
                    ch_num = ci + 1
                    ch_file = os.path.join(ch_outlines_dir, f"chapter_{ch_num:03d}.md")
                    if not read_file(ch_file):
                        pending.append((ch_num, ch))

                for bi in range(0, len(pending), MAX_CHAPTERS_PER_BATCH):
                    _check_stop(stop_event)
                    batch = pending[bi:bi + MAX_CHAPTERS_PER_BATCH]
                    ch_range = f"{batch[0][0]}-{batch[-1][0]}"
                    log.info(f"    -> 批量提取第{ch_range}章章纲（{len(batch)}章）...")
                    outlines = _generate_chapter_outlines_batch(batch, llm)
                    for ch_num, outline in outlines.items():
                        ch_file = os.path.join(ch_outlines_dir, f"chapter_{ch_num:03d}.md")
                        write_file(ch_file, outline)
                    for ch_num, ch in batch:
                        ch_file = os.path.join(ch_outlines_dir, f"chapter_{ch_num:03d}.md")
                        if not read_file(ch_file):
                            log.info(f"    -> 第{ch_num}章未在批量结果中，单独生成...")
                            prompt = PromptLoader.load(
                                "chapter_outline_extract",
                                chapters_text=f"=== 第{ch_num}章 ===\n{ch['content']}",
                            )
                            result = normalize_text(llm.generate(prompt))
                            write_file(ch_file, result)
                    log.info(f"    -> 第{ch_range}章章纲已保存")
    else:
        log.info(f"\n--- 阶段二：跳过章纲提取（skip_chapter_outlines=True） ---")

    # 6. 汇总生成大纲
    log.info(f"\n--- 阶段三：汇总生成大纲 ---")
    extract_novel_outline(volume_outlines, llm, outlines_dir)

    log.info(f"\n>>> 参考小说大纲梳理完成 <<<")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="从参考小说中梳理大纲和卷纲")
    parser.add_argument("--novel", type=str, required=True, help="工作区名称")
    parser.add_argument("--batch-size", type=int, default=30, help="每批章节数（默认30）")
    parser.add_argument("--txt-path", type=str, default=None, help="小说文件路径（默认使用工作区 reference/sample_novel.txt）")
    parser.add_argument("--output-dir", type=str, default=None, help="输出目录（默认使用工作区 reference/）")
    args = parser.parse_args()

    ws = init_workspace(args.novel)
    run_outline_build(
        txt_path=args.txt_path or ws.reference_sample,
        output_dir=args.output_dir or ws.reference,
        batch_size=args.batch_size,
    )
