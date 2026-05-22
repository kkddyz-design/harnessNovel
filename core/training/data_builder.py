import json
import os
import re
from core.llm_provider import LLMProvider
from core.context_manager import ContextManager
from core.prompt_loader import PromptLoader
from core.text_utils import normalize_text, parse_json_response

class DataBuilder:
    def __init__(self, llm: LLMProvider, base_dir="file_system", training_dir="training"):
        self.llm = llm
        self.context_manager = ContextManager(base_dir=base_dir)
        self.training_dir = training_dir

    def _read_training_file(self, filename):
        path = os.path.join(self.training_dir, filename)
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return f.read().strip()
        return f"[{filename} Not Found]"

    def build_from_txt(self, txt_path, output_file="training_data.json", recent_n=3, max_chapters=None):
        """
        读取外部的 txt 格式小说文件，并切分成章节列表，然后调用 build_training_data
        集成 split_novel 逻辑，支持处理带有 [file content begin] 标记和标准的 "X.第X章" 格式。
        如果指定了 max_chapters，则只读取前 max_chapters 章。
        """
        if not os.path.exists(txt_path):
            raise FileNotFoundError(f"未找到 txt 文件: {txt_path}")
            
        with open(txt_path, "r", encoding="utf-8") as f:
            text = f.read()
            
        # 去除可能的文件头标记
        begin_marker = "[file content begin]"
        end_marker = "[file content end]"
        start_pos = text.find(begin_marker)
        if start_pos != -1:
            text = text[start_pos + len(begin_marker):]
        # 去除末尾的标记
        end_pos = text.rfind(end_marker)
        if end_pos != -1:
            text = text[:end_pos]

        # 匹配章节标题的模式，例如：
        # 1.第1章 大玄历二月初二
        # 2.第2章 大道之章
        chapter_pattern = re.compile(r'^\d+\.第\d+[章回节卷]\s.+', re.MULTILINE)

        # 找到所有章节标题的起始位置和匹配对象
        matches = list(chapter_pattern.finditer(text))
        if not matches:
            # 如果没有匹配到 "1.第1章" 格式，尝试回退到普通的 "第X章" 格式
            fallback_pattern = re.compile(r"(第[一二三四五六七八九十百千0-9]+[章回节卷].*?)\n")
            parts = fallback_pattern.split(text)
            chapters = []
            if parts[0].strip():
                chapters.append(parts[0].strip())
            for i in range(1, len(parts), 2):
                chapter_title = parts[i].strip()
                chapter_body = parts[i+1].strip() if i+1 < len(parts) else ""
                if chapter_title or chapter_body:
                    chapters.append(f"{chapter_title}\n{chapter_body}")
        else:
            chapters = []
            for i, match in enumerate(matches):
                start = match.start()
                if i + 1 < len(matches):
                    end = matches[i + 1].start()
                else:
                    end = len(text)
                
                # 提取章节内容
                chapter_content = normalize_text(text[start:end])
                chapters.append(chapter_content)
                
        # 截取前 max_chapters 章
        if max_chapters is not None:
            chapters = chapters[:max_chapters]
                
        print(f"[Data Builder] 成功从 {txt_path} 中解析出 {len(chapters)} 章内容。")
        
        if not chapters:
            print("[Data Builder] 警告：未能解析出任何章节，请检查 txt 文件的章节格式。")
            return []
            
        return self.build_training_data(chapters, output_file, recent_n)

    def build_chapter_training_data(self, source_data_file="training/real_training_data.json", output_file="training/chapter_training_data.json"):
        """
        基于已生成的正文训练数据，构造用于训练“章纲生成”的训练数据集。
        提取逻辑：
        - 以“卷纲中的一个故事段落”为粒度进行聚合。
        - 输入特征 (context_data)：该段落起始时的历史章节内容、单段卷纲、世界观、人物档案、线索池。
        - 目标标签 (label)：大模型基于真实小说内容总结出的该段落内所有章节的章纲集合。
        """
        if not os.path.exists(source_data_file):
            raise FileNotFoundError(f"未找到正文训练数据源文件: {source_data_file}")
            
        print(f"[Data Builder] 正在从 {source_data_file} 中提取数据以构造章纲训练集(按段落聚合)...")
        
        with open(source_data_file, "r", encoding="utf-8") as f:
            source_data = json.load(f)
            
        # 先从训练目录读取一次完整的 volume_outline 以便划分段落边界
        full_volume_outline = self._read_training_file("volume_outline.md")
        
        # 解析所有的段落区间
        pattern = re.compile(r'([一二三四五六七八九十百千万]+、.*?[（\(]第(\d+)章\s*-\s*第(\d+)章[）\)].*?)(?=\n[一二三四五六七八九十百千万]+、|$)', re.DOTALL)
        segments = []
        for match in pattern.finditer(full_volume_outline):
            segments.append({
                "start": int(match.group(2)),
                "end": int(match.group(3)),
                "text": match.group(1).strip()
            })
            
        chapter_training_data = []
        
        # 按照段落聚合数据
        for seg in segments:
            seg_start = seg["start"]
            seg_end = seg["end"]
            
            # 找出该段落内包含的所有源数据 (注意 i 是索引，章节号通常是 i+1)
            seg_items = [item for i, item in enumerate(source_data) if seg_start <= (i + 1) <= seg_end]
            
            if not seg_items:
                continue
                
            # 取该段落第一章之前的状态作为起始 Context
            first_item = seg_items[0]
            start_context = first_item.get("context_data", {}).copy()
            
            # 严格替换卷纲为单一段落 (不包含下一段)
            # 因为我们在 start_context 里的 current_chapter 实际上是 seg_start
            single_segment_outline = self.context_manager.extract_relevant_volume_outline(
                full_volume_outline, seg_start, include_next=False
            )
            start_context["volume_outline"] = single_segment_outline
            start_context["future_outline"] = f"（待生成第 {seg_start} 章至第 {seg_end} 章的详细章纲）"
            
            # 注入章纲专属规则，并移除不需要的正文规则 agents_md
            chapter_agents_md = self.context_manager._read_file("CHAPTER_AGENTS.md", "chapter_agents_md")
            start_context["chapter_agents_md"] = chapter_agents_md
            if "agents_md" in start_context:
                del start_context["agents_md"]
            
            # 聚合同一段落内所有章节的真实章纲，作为目标的 Label
            aggregated_label = []
            for idx, item in enumerate(seg_items):
                chap_num = seg_start + idx
                chap_outline = item.get("context_data", {}).get("future_outline", "")
                aggregated_label.append(f"【第{chap_num}章 章纲】\n{chap_outline}")
                
            data_item = {
                "segment_range": f"{seg_start}-{seg_end}",
                "context_data": start_context,
                "label": "\n\n".join(aggregated_label)
            }
            chapter_training_data.append(data_item)
            
        os.makedirs(os.path.dirname(output_file) if os.path.dirname(output_file) else ".", exist_ok=True)
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(chapter_training_data, f, ensure_ascii=False, indent=4)
            
        print(f"[Data Builder] 成功提取了 {len(chapter_training_data)} 个故事段落的章纲训练数据，已保存至 {output_file}。")
        return chapter_training_data

    def build_training_data(self, chapter_texts, output_file="training_data.json", recent_n=3):
        """
        利用大模型滚动阅读经典小说，构造多条训练数据。
        按照如下流程：
        1、system_prompt、novel_outline、volume_outline 维持不变 
        2、循环执行：
           - 步骤1：读取当前章节内容作为 label，调用大模型生成 future_outline，构建一条数据
           - 步骤2：根据章节内容更新 clues、characters、dynamic_worldview、plot_summary、recent_chapters_content
           - 步骤3：继续执行
        """
        print("[Data Builder] 正在解析经典小说内容，构造训练数据集...")
        
        # 1. 维持不变的初始状态
        
        # 动态读取 system_prompt, novel_outline, volume_outline, dynamic_worldview
        system_prompt_content = self.context_manager._read_file("system_prompt.md", "system_prompt")
        if "[system_prompt.md Not Found]" in system_prompt_content:
            system_prompt_content = "你是一个顶级的网文小说家，擅长细腻的情感描写和古典仙侠的意境渲染。"

        novel_outline_content = self._read_training_file("novel_outline.md")
        if "[novel_outline.md Not Found]" in novel_outline_content:
            novel_outline_content = "【小说大纲】草庙村少年张小凡经历惨案后拜入青云门，历经磨难，最终成长为一代宗师。"

        volume_outline_content = self._read_training_file("volume_outline.md")
        if "[volume_outline.md Not Found]" in volume_outline_content:
            volume_outline_content = "【卷纲】青云山篇，描写其在门派内的平凡生活与初涉修真的见闻。"

        dynamic_worldview_content = self.context_manager._read_file("dynamic_worldview.md", "dynamic_worldview")
        if "[dynamic_worldview.md Not Found]" in dynamic_worldview_content:
            dynamic_worldview_content = "【动态世界观】神州浩土，正道以青云门、天音寺、焚香谷为首。"
            
        agents_md_content = self.context_manager._read_file("AGENTS.md", "agents_md")
        if "[AGENTS.md Not Found]" in agents_md_content:
            agents_md_content = "当前暂无特定规则"
            
        current_context_data = {
            "system_prompt": system_prompt_content,
            "agents_md": agents_md_content,
            "novel_outline": novel_outline_content,
            "volume_outline": volume_outline_content,
            "dynamic_worldview": dynamic_worldview_content,
            "future_outline": "无",
            "characters": "无",
            "clues": "无",
            "plot_summary": "【前文剧情总结】暂无。",
            "recent_chapters_content": "无"
        }
        
        training_data = []
        recent_chapters = []
        
        # 尝试加载已有的训练数据，实现断点续传/增量追加
        if os.path.exists(output_file):
            try:
                with open(output_file, "r", encoding="utf-8") as f:
                    training_data = json.load(f)
                if training_data and isinstance(training_data, list):
                    print(f"[Data Builder] 发现已有的训练数据 ({len(training_data)} 章)，将尝试基于此状态继续生成。")
                    # 恢复 current_context_data 状态
                    last_item = training_data[-1]
                    current_context_data = last_item.get("context_data", current_context_data).copy()

                    # 从已有训练数据的最后 recent_n 条重建 recent_chapters
                    # 不能用 split("\n\n")，因为章节正文内部也有段落换行会导致碎片化
                    rebuild_items = training_data[-recent_n:] if len(training_data) >= recent_n else training_data[:]
                    rebuild_start = len(training_data) - len(rebuild_items)
                    recent_chapters = []
                    for idx, item in enumerate(rebuild_items):
                        chap_num = rebuild_start + idx + 1
                        recent_chapters.append(f"--- 章节: 第{chap_num}章 ---\n{item['label']}")
            except Exception as e:
                print(f"[Data Builder] 警告：无法加载已有训练数据 ({e})，将重新开始。")
                training_data = []
                recent_chapters = []
        
        start_idx = len(training_data)
        if start_idx >= len(chapter_texts):
            print("[Data Builder] 所有的章节数据均已生成，无需继续。")
            return training_data
            
        # 2. 循环执行构造
        for i in range(start_idx, len(chapter_texts)):
            chapter_content = chapter_texts[i]
            current_chapter_num = i + 1
            print(f"  -> 正在处理第 {current_chapter_num} 章...")
            
            # 动态截取卷纲（当前段落 + 下一个段落）
            relevant_volume_outline = self.context_manager.extract_relevant_volume_outline(volume_outline_content, current_chapter_num)
            current_context_data["volume_outline"] = relevant_volume_outline
            
            # --- 步骤1：读取当前章节内容作为 label，并调用大模型总结作为 future_outline ---
            summary_prompt = PromptLoader.load("summary", chapter_content=chapter_content)
            
            # 模拟大模型总结（实际中 llm.generate 返回总结文本）
            future_outline = self.llm.generate(summary_prompt)
            if future_outline == "LLM生成的通用回复内容。":
                future_outline = f"第{i+1}章意图总结：主角经历了一些事情..."
                
            # 加载到 context_data 中
            current_context_data["future_outline"] = future_outline
            
            # 成功构建一条训练数据保存到本地（在内存列表中）
            # 此时的 current_context_data 中的 recent_chapters_content 仅包含上一章为止的内容
            data_item = {
                "context_data": current_context_data.copy(),
                "label": normalize_text(chapter_content)
            }
            training_data.append(data_item)
            
            # --- 步骤2：根据读取的章节内容，对状态进行更新 ---
            update_prompt = PromptLoader.load(
                "update",
                clues=current_context_data['clues'],
                characters=current_context_data['characters'],
                dynamic_worldview=current_context_data['dynamic_worldview'],
                plot_summary=current_context_data['plot_summary'],
                chapter_content=chapter_content
            )
            # 带重试的状态更新：最多重试2次
            max_retries = 2
            updated_state = None
            for attempt in range(max_retries + 1):
                update_result = self.llm.generate(update_prompt, is_json=True)
                try:
                    updated_state = parse_json_response(update_result)
                    break
                except Exception as e:
                    if attempt < max_retries:
                        print(f"[Data Builder] JSON 解析失败（第{attempt+1}次），重试中... 错误：{e}")
                    else:
                        print(f"[Data Builder] JSON 解析失败，已重试{max_retries}次，回退到模拟更新。错误：{e}")
                        updated_state = None

            if updated_state:
                if "clues" in updated_state:
                    current_context_data["clues"] = updated_state["clues"]
                if "characters" in updated_state:
                    current_context_data["characters"] = updated_state["characters"]
                if "dynamic_worldview" in updated_state:
                    current_context_data["dynamic_worldview"] = updated_state["dynamic_worldview"]
                if "plot_summary" in updated_state:
                    current_context_data["plot_summary"] = updated_state["plot_summary"]
            else:
                # 模拟状态更新（防错回退机制）
                current_context_data["clues"] += f"\n[第{i+1}章更新] 发现了新的线索与伏笔。"
                current_context_data["characters"] += f"\n[第{i+1}章更新] 人物关系发生推进。"
                current_context_data["dynamic_worldview"] += f"\n[第{i+1}章更新] 场景/世界观细节补充。"
                current_context_data["plot_summary"] += f"\n[第{i+1}章摘要] {future_outline}"
            
            # 更新近期章节内容 (近N章的完整内容，保证延续性)
            recent_chapters.append(f"--- 章节: 第{i+1}章 ---\n{normalize_text(chapter_content)}")
            if len(recent_chapters) > recent_n:
                recent_chapters.pop(0)
            current_context_data["recent_chapters_content"] = "\n\n".join(recent_chapters)
            
            # 步骤3：继续下一章循环...
            # 立即保存一次数据，避免内存积压和意外丢失
            os.makedirs(os.path.dirname(output_file) if os.path.dirname(output_file) else ".", exist_ok=True)
            with open(output_file, "w", encoding="utf-8") as f:
                json.dump(training_data, f, ensure_ascii=False, indent=4)
            print(f"  -> 第 {current_chapter_num} 章训练数据已实时保存。")

        print(f"[Data Builder] 训练数据集已全部生成并保存至 {output_file}")
        return training_data
