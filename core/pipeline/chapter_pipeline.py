import json
import os
import concurrent.futures
from core.agents import ChapterDraftingAgent, ChapterComparisonAgent, OptimizerAgent, SelfCheckAgent
from core.context_manager import ContextManager
from core.prompt_loader import PromptLoader
from core.text_utils import normalize_text, clean_markdown_symbols

class ChapterTrainingPipeline:
    def __init__(self, agent_configs=None, base_dir="file_system"):
        self.base_dir = base_dir
        self.context_manager = ContextManager(base_dir=base_dir)

        default_config = {"model": None, "base_url": None, "api_key": None}
        agent_configs = agent_configs or {}

        drafting_config = agent_configs.get("drafting", default_config)
        comparison_config = agent_configs.get("comparison", default_config)
        optimizer_config = agent_configs.get("optimizer", default_config)
        self_check_config = agent_configs.get("self_check", default_config)

        self.chapter_drafting_agent = ChapterDraftingAgent(**drafting_config)
        self.chapter_comparison_agent = ChapterComparisonAgent(**comparison_config)
        self.optimizer_agent = OptimizerAgent(**optimizer_config)
        self.self_check_agent = SelfCheckAgent(**self_check_config)

    def load_training_data(self, data_file="training/chapter_training_data.json"):
        if not os.path.exists(data_file):
            raise FileNotFoundError(f"Chapter Training data file {data_file} not found.")
        with open(data_file, "r", encoding="utf-8") as f:
            return json.load(f)

    def _process_single_sample(self, idx, data, current_rules):
        """
        处理单个章纲样本的方法，支持并行调用。
        """
        print(f"\n--- [Thread] 开始处理章纲数据样本 {idx+1} ---")
        context_data = data["context_data"]
        label = data["label"]

        # 将最新的章纲专门规则注入
        context_data["chapter_agents_md"] = current_rules

        # 临时 ContextManager 避免线程冲突
        local_context_manager = ContextManager(base_dir=self.base_dir)
        local_context_manager.set_context_override(context_data)

        # 组装完整的上下文
        full_context = local_context_manager.build_full_context()

        # Agent生成章纲
        generated_chapter_outline = self.chapter_drafting_agent.generate_draft(full_context)

        # 自检 + 修订
        check_result = self.self_check_agent.check(generated_chapter_outline, full_context)
        if check_result.get("violations"):
            generated_chapter_outline, _ = self.self_check_agent.revise(generated_chapter_outline, check_result)

        # Comparison 审计生成的章纲与真实章纲的偏差
        eval_result = self.chapter_comparison_agent.evaluate_training_sample(generated_chapter_outline, label, full_context)

        feedback = eval_result.get("feedback", "无有效反馈")
        score = eval_result.get("average_score", 0)

        print(f"样本 {idx+1} 章纲审计完成。各项得分: "
              f"情节推进:{eval_result.get('plot_push_score',0)} "
              f"人物弧光:{eval_result.get('character_arc_score',0)} "
              f"冲突张力:{eval_result.get('conflict_score',0)} "
              f"悬念铺垫:{eval_result.get('suspense_score',0)} "
              f"细节颗粒度:{eval_result.get('detail_granularity_score',0)} "
              f"-> 平均分:{score:.2f}")

        return {
            "idx": idx,
            "score": score,
            "feedback": feedback,
            "attribution": eval_result.get("attribution", "drafting_error"),
            "rule_suggestions": eval_result.get("rule_suggestions", [])
        }

    def run_training_loop(self, data_file="training/chapter_training_data.json", max_epochs=3, batch_size=5, max_workers=2):
        """
        基于多轮循环的【章纲】训练评估 pipeline。
        """
        print(f"\n================ 开始 章纲生成 (Chapter Outline) 训练 Pipeline ================")
        dataset = self.load_training_data(data_file)

        for epoch in range(1, max_epochs + 1):
            print(f"\n>>>>>>>> 第 {epoch}/{max_epochs} 轮 (Epoch) 章纲训练 <<<<<<<<")

            epoch_score = 0

            for batch_start in range(0, len(dataset), batch_size):
                batch_data = dataset[batch_start:batch_start + batch_size]
                print(f"\n--- 准备处理章纲批次 [{batch_start+1} - {batch_start+len(batch_data)}]，并行度: {max_workers} ---")

                # 读取当前批次使用的章纲专属规则
                current_rules = "当前暂无特定章纲生成规则"
                agents_md_path = os.path.join(self.base_dir, "CHAPTER_AGENTS.md")
                if os.path.exists(agents_md_path):
                    with open(agents_md_path, "r", encoding="utf-8") as f:
                        current_rules = f.read()

                batch_feedbacks = []
                batch_score = 0
                batch_results = []

                # 并发执行该批次的章纲生成与审计
                with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
                    futures = {
                        executor.submit(self._process_single_sample, batch_start + i, data, current_rules): (batch_start + i)
                        for i, data in enumerate(batch_data)
                    }

                    for future in concurrent.futures.as_completed(futures):
                        try:
                            result = future.result()
                            batch_feedbacks.append(result["feedback"])
                            batch_score += result["score"]
                            epoch_score += result["score"]
                            batch_results.append(result)
                        except Exception as exc:
                            print(f"处理章纲样本时发生异常: {exc}")

                # 批次汇总与优化
                avg_batch_score = batch_score / len(batch_feedbacks) if batch_feedbacks else 0
                print(f"\n[Batch] 当前章纲批次处理完成 ({len(batch_feedbacks)} 个样本), 平均分: {avg_batch_score:.2f}")

                if avg_batch_score < 80:
                    print(f"[Pipeline] 章纲批次平均分偏低，触发 Optimizer Agent 更新 CHAPTER_AGENTS.md...")

                    # 收集所有 rule_suggestions
                    all_suggestions = []
                    for r in batch_results:
                        all_suggestions.extend(r.get("rule_suggestions", []))

                    import json as _json
                    summary_feedback = _json.dumps({
                        "batch_avg_score": avg_batch_score,
                        "sample_feedbacks": batch_feedbacks,
                        "rule_suggestions": all_suggestions
                    }, ensure_ascii=False, indent=2)

                    # 针对章纲复用现有的 Optimizer
                    prompt = PromptLoader.load(
                        "chapter_optimizer",
                        current_agents_md=current_rules,
                        feedback=summary_feedback
                    )
                    optimization_rules = self.optimizer_agent.generate(prompt)

                    # 清理 markdown 代码块
                    if optimization_rules.startswith("```markdown"):
                        optimization_rules = optimization_rules[len("```markdown"):].strip()
                    elif optimization_rules.startswith("```"):
                        optimization_rules = optimization_rules[len("```"):].strip()
                    if optimization_rules.endswith("```"):
                        optimization_rules = optimization_rules[:-3].strip()

                    # 清洗 Markdown 格式符号并规范化
                    optimization_rules = clean_markdown_symbols(optimization_rules)
                    optimization_rules = normalize_text(optimization_rules)

                    # 去除可能的寒暄前缀（确保以 # 开头或直接是规则内容）
                    title_marker = "# 章纲写作规范"
                    if title_marker in optimization_rules:
                        optimization_rules = optimization_rules[optimization_rules.index(title_marker):]

                    with open(agents_md_path, "w", encoding="utf-8") as f:
                        f.write(optimization_rules)
                    print(f"[Optimizer] 已融合更新 {agents_md_path}")

                else:
                    print(f"[Pipeline] 章纲批次平均分良好，无需本轮优化。")

            # Epoch 结算
            avg_epoch_score = epoch_score / len(dataset)
            print(f"\n[Epoch {epoch} 结算] 全局章纲平均得分: {avg_epoch_score:.2f}")

            if avg_epoch_score >= 80:
                print(f"\n[Pipeline] 全局生成的章纲与 Label 已经较为接近，提前停止训练。")
                break

        print(f"\n================ 章纲生成训练 Pipeline 结束 ================\n")
