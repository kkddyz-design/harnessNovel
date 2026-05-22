import json
from .base_agent import BaseAgent
from core.prompt_loader import PromptLoader
from core.text_utils import parse_json_response

class ComparisonAgent(BaseAgent):
    def __init__(self, base_url=None, api_key=None, model="mock-model"):
        super().__init__(name="Comparison Agent", base_url=base_url, api_key=api_key, model=model)

    def audit_draft(self, draft, chapter_intent, context):
        """
        Comparison Agent：负责审计初稿内容与预期是否相符
        （用于正常的创作环节，只提意见，不打分）
        """
        prompt = PromptLoader.load(
            "comparison_audit",
            context=context,
            chapter_intent=chapter_intent,
            draft=draft
        )
        return self.generate(prompt)

    def evaluate_training_sample(self, generated_content, target_label, context, max_retries=2):
        """
        用于训练 Pipeline：调用大模型自动审计评分，并结合 context 进行归因分析。
        带重试机制，最多重试 max_retries 次。
        """
        prompt = PromptLoader.load(
            "comparison_evaluate",
            context=context,
            target_label=target_label,
            generated_content=generated_content
        )

        for attempt in range(max_retries + 1):
            result_str = self.llm.generate(prompt, is_json=True)
            try:
                result_json = parse_json_response(result_str)

                total_score = (
                    result_json.get("word_count_score", 0) +
                    result_json.get("plot_score", 0) +
                    result_json.get("dialogue_score", 0) +
                    result_json.get("character_score", 0) +
                    result_json.get("style_score", 0) +
                    result_json.get("suspense_score", 0)
                ) / 6.0

                result_json["average_score"] = total_score
                # 确保新字段有默认值
                result_json.setdefault("attribution", "drafting_error")
                result_json.setdefault("attribution_detail", "")
                result_json.setdefault("rule_suggestions", [])
                return result_json
            except Exception as e:
                if attempt < max_retries:
                    print(f"[{self.name}] 评分 JSON 解析失败（第{attempt+1}次），重试中... 错误: {e}")
                else:
                    print(f"[{self.name}] 评分 JSON 解析失败，已重试{max_retries}次。错误: {e}")
                    return {
                        "word_count_score": 0, "plot_score": 0, "dialogue_score": 0, "character_score": 0,
                        "style_score": 0, "suspense_score": 0,
                        "average_score": 0, "feedback": f"大模型审计输出格式异常，未能提取有效反馈。原始内容: {result_str}",
                        "attribution": "drafting_error", "attribution_detail": "",
                        "rule_suggestions": []
                    }
