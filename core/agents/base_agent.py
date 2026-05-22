from ..llm_provider import LLMProvider

class BaseAgent:
    def __init__(self, name="BaseAgent", base_url=None, api_key=None, model="mock-model"):
        self.name = name
        self.llm = LLMProvider(model=model, base_url=base_url, api_key=api_key)

    def generate(self, prompt, temperature=0.7):
        print(f"[{self.name}] 正在生成内容...")
        return self.llm.generate(prompt, temperature=temperature)
