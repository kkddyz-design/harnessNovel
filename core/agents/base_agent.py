from ..llm_provider import LLMProvider
from core.text_utils import parse_json_response


class BaseAgent:
    def __init__(self, name="BaseAgent", base_url=None, api_key=None, model=None):
        self.name = name
        self.llm = LLMProvider(model=model, base_url=base_url, api_key=api_key)

    def generate(self, prompt, temperature=0.7):
        print(f"[{self.name}] 正在生成内容...")
        return self.llm.generate(prompt, temperature=temperature)

    def _generate_json_with_retry(self, prompt, max_retries=2, default_result=None):
        """Call LLM with JSON output, retry on parse failure. Returns parsed dict."""
        for attempt in range(max_retries + 1):
            result_str = self.llm.generate(prompt, is_json=True)
            try:
                return parse_json_response(result_str)
            except Exception as e:
                if attempt < max_retries:
                    print(f"[{self.name}] JSON 解析失败（第{attempt+1}次），重试中... 错误: {e}")
                else:
                    print(f"[{self.name}] JSON 解析失败，已重试{max_retries}次。错误: {e}")
                    return default_result or {}
