import json
import os
import concurrent.futures
from core.agents.drafting_agent import DraftingAgent
from core.agents.comparison_agent import ComparisonAgent
from core.agents.optimizer_agent import OptimizerAgent
from core.agents.self_check_agent import SelfCheckAgent
from core.context_manager import ContextManager

class TrainingPipeline:
    def __init__(self, agent_configs=None, base_dir="file_system"):
        self.base_dir = base_dir
        self.context_manager = ContextManager(base_dir=base_dir)

        default_config = {"model": "mock-model", "base_url": None, "api_key": None}
        agent_configs = agent_configs or {}

        drafting_config = agent_configs.get("drafting", default_config)
        comparison_config = agent_configs.get("comparison", default_config)
        optimizer_config = agent_configs.get("optimizer", default_config)
        self_check_config = agent_configs.get("self_check", default_config)

        self.drafting_agent = DraftingAgent(**drafting_config)
        self.comparison_agent = ComparisonAgent(**comparison_config)
        self.optimizer_agent = OptimizerAgent(**optimizer_config)
        self.self_check_agent = SelfCheckAgent(**self_check_config)

    def load_training_data(self, data_file="training_data.json"):
        if not os.path.exists(data_file):
            raise FileNotFoundError(f"Training data file {data_file} not found.")
        with open(data_file, "r", encoding="utf-8") as f:
            return json.load(f)

    def _process_single_sample(self, idx, data, current_rules):
        """
        处理单个样本的内部方法，支持并行调用。
        """
        print(f"\n--- [Thread] 开始处理数据样本 {idx+1} ---")
        context_data = data["context_data"]
        label = data["label"]
        
        # 动态将最新的规则更新到该样本的上下文数据中
        context_data["agents_md"] = current_rules
        
        # 为了避免多线程时 context_manager 状态冲突，这里临时创建一个专用的 ContextManager 实例
        local_context_manager = ContextManager(base_dir=self.base_dir)
        local_context_manager.set_mock_data(context_data)
        full_context = local_context_manager.build_full_context()
        
        generated_content = self.drafting_agent.generate_draft(full_context)

        # 自检 + 修订
        check_result = self.self_check_agent.check(generated_content, full_context)
        if check_result.get("violations"):
            generated_content, _ = self.self_check_agent.revise(generated_content, check_result)

        # 审计员对生成内容与真实Label进行对比打分
        eval_result = self.comparison_agent.evaluate_training_sample(generated_content, label, full_context)
        
        feedback = eval_result.get("feedback", "无有效反馈")
        score = eval_result.get("average_score", 0)
        attribution = eval_result.get("attribution", "drafting_error")
        rule_suggestions = eval_result.get("rule_suggestions", [])

        print(f"样本 {idx+1} 审计完成。各项得分: "
              f"字数:{eval_result.get('word_count_score',0)} "
              f"情节:{eval_result.get('plot_score',0)} "
              f"对话:{eval_result.get('dialogue_score',0)} "
              f"人物:{eval_result.get('character_score',0)} "
              f"文风:{eval_result.get('style_score',0)} "
              f"悬念:{eval_result.get('suspense_score',0)} "
              f"-> 平均分:{score:.2f} 归因:{attribution}")

        return {
            "idx": idx,
            "score": score,
            "feedback": feedback,
            "attribution": attribution,
            "rule_suggestions": rule_suggestions
        }

    def run_training_loop(self, data_file="training_data.json", max_epochs=3, batch_size=5, max_workers=2):
        """
        基于多轮循环的训练评估 pipeline。
        多轮循环，直至训练数据集中章节生成的内容与label较为接近。
        增加 batch_size 参数，按批次进行评估和 Optimizer 的更新，避免反馈内容过长。
        """
        print(f"\n================ 开始训练 Pipeline ================")
        dataset = self.load_training_data(data_file)
        
        for epoch in range(1, max_epochs + 1):
            print(f"\n>>>>>>>> 第 {epoch}/{max_epochs} 轮 (Epoch) 训练 <<<<<<<<")
            
            epoch_score = 0  
            batch_feedbacks = []
            batch_score = 0
            
            for batch_start in range(0, len(dataset), batch_size):
                batch_data = dataset[batch_start:batch_start + batch_size]
                print(f"\n--- 准备处理批次 [{batch_start+1} - {batch_start+len(batch_data)}]，并行度: {max_workers} ---")
                
                # 读取当前批次使用的规则
                current_rules = "当前暂无特定规则"
                agents_md_path = os.path.join(self.base_dir, "AGENTS.md")
                if os.path.exists(agents_md_path):
                    with open(agents_md_path, "r", encoding="utf-8") as f:
                        current_rules = f.read()
                        
                batch_feedbacks = []
                batch_score = 0
                batch_results = []

                # 使用线程池并发执行该批次
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
                            print(f"处理样本时发生异常: {exc}")

                # 批次执行完毕后，进行汇总评估和优化
                avg_batch_score = batch_score / len(batch_feedbacks) if batch_feedbacks else 0
                print(f"\n[Batch] 当前批次处理完成 ({len(batch_feedbacks)} 个样本), 平均分: {avg_batch_score:.2f}")

                if avg_batch_score < 80:
                    print(f"[Pipeline] 批次平均分偏低，触发 Optimizer Agent 更新训练参数...")
                    # 按 attribution 分组收集 rule_suggestions
                    drafting_suggestions = []
                    summary_suggestions = []
                    update_suggestions = []
                    for r in batch_results:
                        for sug in r.get("rule_suggestions", []):
                            target = sug.get("target", "AGENTS.md")
                            if target == "summary_prompt":
                                summary_suggestions.append(sug)
                            elif target == "update_prompt":
                                update_suggestions.append(sug)
                            else:
                                drafting_suggestions.append(sug)

                    # 按归因分组依次调用 optimizer
                    import json as _json
                    attribution_groups = [
                        ("drafting_error", drafting_suggestions),
                        ("summary_error", summary_suggestions),
                        ("update_error", update_suggestions),
                    ]
                    for attr_type, suggestions in attribution_groups:
                        if not suggestions:
                            continue
                        structured_feedback = _json.dumps({
                            "batch_avg_score": avg_batch_score,
                            "sample_feedbacks": batch_feedbacks,
                            "rule_suggestions": suggestions
                        }, ensure_ascii=False, indent=2)
                        self.optimizer_agent.optimize_parameters(
                            structured_feedback, base_dir=self.base_dir, attribution=attr_type
                        )
                else:
                    print(f"[Pipeline] 批次平均分良好，无需本轮优化。")
            
            # Epoch 结算
            avg_epoch_score = epoch_score / len(dataset)
            print(f"\n[Epoch {epoch} 结算] 全局平均接近度得分: {avg_epoch_score:.2f}")
            
            if avg_epoch_score >= 80:  # 假设得分>=80认为生成的内容与label较为接近
                print(f"\n[Pipeline] 全局生成内容与 Label 已经较为接近，提前停止训练优化。")
                break
        
        print(f"\n================ 训练 Pipeline 结束 ================\n")
