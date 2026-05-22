from .base_agent import BaseAgent
from core.prompt_loader import PromptLoader

class DraftingAgent(BaseAgent):
    def __init__(self, base_url=None, api_key=None, model="mock-model"):
        super().__init__(name="Drafting Agent", base_url=base_url, api_key=api_key, model=model)

    def generate_draft(self, context):
        """
        Drafting Agent：根据上下文完成章节初稿的设计
        """
        prompt = PromptLoader.load("drafting", context=context)
        return self.generate(prompt)
