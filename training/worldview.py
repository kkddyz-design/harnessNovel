"""世界观提取模块：从参考小说按卷提取世界观，汇总为完整世界观。"""

import sys
import os
import glob
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))

from core.llm_provider import LLMProvider
from core.prompt_loader import PromptLoader
from core.config import ConfigLoader
from core.text_utils import normalize_text, read_file, write_file
from log.logger import get_logger

log = get_logger()


def _get_lite_llm():
    """获取辅助任务 LLM（flash 模型）。"""
    config = ConfigLoader.get_adaptive_builder_lite_config()
    if not config:
        config = ConfigLoader.get_adaptive_builder_config()
    if not config.get("api_key"):
        config["api_key"] = os.getenv("OPENAI_API_KEY")
    if not config.get("api_key"):
        log.info("错误：未检测到 API Key。")
        return None
    return LLMProvider(**config)


def gen_worldview(ws, stop_event=None):
    """按卷提取世界观，再汇总为完整世界观。"""
    from training.reference_finder import list_reference_volumes, load_reference_volume_outline
    from training.outline_builder import _check_stop, ImportInterrupted

    log.info(">>> 提取参考小说世界观 <<<")

    worldview_dir = os.path.join(ws.file_system, "worldviews")
    aggregated_path = os.path.join(ws.file_system, "reference_worldview.md")

    ref_volumes = list_reference_volumes(ws.reference_outlines)
    if not ref_volumes:
        log.info("错误：未找到参考小说卷数据。请先运行 outline_builder.py。")
        return

    llm = _get_lite_llm()
    if not llm:
        return

    log.info(">>> 按卷提取参考小说世界观 <<<")
    os.makedirs(worldview_dir, exist_ok=True)
    volume_worldviews = []

    for vol in ref_volumes:
        _check_stop(stop_event)
        vol_idx = vol["vol_idx"]
        vol_title = vol["title"]
        vol_wv_path = os.path.join(worldview_dir, f"vol_{vol_idx:02d}_worldview.md")

        existing = read_file(vol_wv_path)
        if existing:
            log.info(f"  卷{vol_idx}世界观已存在，跳过。")
            volume_worldviews.append({"vol_idx": vol_idx, "title": vol_title, "content": existing})
            continue

        log.info(f"  提取卷{vol_idx}（{vol_title}）世界观...")
        vol_outline = load_reference_volume_outline(ws.reference_outlines, vol_idx)

        batch_files = sorted(glob.glob(os.path.join(vol["dir_path"], "batch_*.md")))
        batch_contents = []
        for bf in batch_files:
            content = read_file(bf)
            if content:
                batch_contents.append(content)

        if not batch_contents:
            log.info(f"  卷{vol_idx}无批次摘要，跳过。")
            continue

        batches_text = "\n\n---\n\n".join(batch_contents)
        prompt = PromptLoader.load(
            "worldview_extract",
            volume_title=vol_title,
            volume_outline=vol_outline or "（无卷纲）",
            batch_summaries=batches_text,
        )
        result = normalize_text(llm.generate(prompt))
        write_file(vol_wv_path, result)
        volume_worldviews.append({"vol_idx": vol_idx, "title": vol_title, "content": result})
        log.info(f"  卷{vol_idx}世界观已保存")

    if not volume_worldviews:
        log.info("错误：未提取到任何卷的世界观。")
        return

    existing_agg = read_file(aggregated_path)
    if existing_agg:
        log.info(f"\n汇总世界观已存在：{aggregated_path}")
        log.info("如需重新生成，请先删除该文件。")
        return

    log.info(f"\n>>> 汇总 {len(volume_worldviews)} 卷世界观 <<<")
    all_wv = "\n\n---\n\n".join(
        f"# {wv['title']}（卷{wv['vol_idx']}）\n{wv['content']}"
        for wv in volume_worldviews
    )

    if len(volume_worldviews) == 1:
        write_file(aggregated_path, volume_worldviews[0]["content"])
    else:
        _check_stop(stop_event)
        prompt = PromptLoader.load("worldview_merge", volume_worldviews=all_wv)
        result = normalize_text(llm.generate(prompt))
        write_file(aggregated_path, result)

    log.info(f"  -> 汇总世界观已保存：{aggregated_path}")
    log.info(f"  -> 按卷世界观保存在：{worldview_dir}/")
