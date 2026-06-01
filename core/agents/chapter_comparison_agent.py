from .comparison_agent import ComparisonAgent
from core.prompt_loader import PromptLoader


_CHAPTER_SCORE_FIELDS = ["plot_push_score", "character_arc_score", "conflict_score",
                          "suspense_score", "detail_granularity_score"]
_CHAPTER_SCORE_COUNT = len(_CHAPTER_SCORE_FIELDS)


class ChapterComparisonAgent(ComparisonAgent):
    def __init__(self, base_url=None, api_key=None, model=None):
        super().__init__(base_url=base_url, api_key=api_key, model=model)
        self.name = "Chapter Comparison Agent"

    def evaluate_training_sample(self, generated_content, target_label, context, max_retries=2):
        prompt = PromptLoader.load("chapter_comparison_evaluate", context=context,
                                   target_label=target_label, generated_content=generated_content)
        result_json = self._generate_json_with_retry(prompt, max_retries)

        if not result_json:
            fallback = dict.fromkeys(_CHAPTER_SCORE_FIELDS + ["average_score"], 0)
            fallback.update({"feedback": "大模型审计输出格式异常，未能提取有效反馈。",
                             "attribution": "drafting_error", "attribution_detail": "",
                             "rule_suggestions": []})
            return fallback

        total_score = sum(result_json.get(f, 0) for f in _CHAPTER_SCORE_FIELDS) / _CHAPTER_SCORE_COUNT
        result_json["average_score"] = total_score
        result_json.setdefault("attribution", "drafting_error")
        result_json.setdefault("attribution_detail", "")
        result_json.setdefault("rule_suggestions", [])
        return result_json
