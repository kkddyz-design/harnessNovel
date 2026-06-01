from .base_agent import BaseAgent
from core.prompt_loader import PromptLoader


_SCORE_FIELDS = ["word_count_score", "plot_score", "dialogue_score", "character_score",
                 "style_score", "suspense_score"]
_SCORE_COUNT = len(_SCORE_FIELDS)


class ComparisonAgent(BaseAgent):
    def __init__(self, base_url=None, api_key=None, model=None):
        super().__init__(name="Comparison Agent", base_url=base_url, api_key=api_key, model=model)

    def audit_draft(self, draft, chapter_intent, context):
        prompt = PromptLoader.load("comparison_audit", context=context,
                                   chapter_intent=chapter_intent, draft=draft)
        return self.generate(prompt)

    def evaluate_training_sample(self, generated_content, target_label, context, max_retries=2, result_str_hook=None):
        prompt = PromptLoader.load("comparison_evaluate", context=context,
                                   target_label=target_label, generated_content=generated_content)
        result_json = self._generate_json_with_retry(prompt, max_retries)

        if not result_json:
            fallback = dict.fromkeys(_SCORE_FIELDS + ["average_score"], 0)
            fallback.update({"feedback": "大模型审计输出格式异常，未能提取有效反馈。",
                             "attribution": "drafting_error", "attribution_detail": "",
                             "rule_suggestions": []})
            return fallback

        total_score = sum(result_json.get(f, 0) for f in _SCORE_FIELDS) / _SCORE_COUNT
        result_json["average_score"] = total_score
        result_json.setdefault("attribution", "drafting_error")
        result_json.setdefault("attribution_detail", "")
        result_json.setdefault("rule_suggestions", [])
        return result_json
