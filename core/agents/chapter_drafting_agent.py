from .base_agent import BaseAgent
from core.prompt_loader import PromptLoader

class ChapterDraftingAgent(BaseAgent):
    def __init__(self, base_url=None, api_key=None, model=None):
        super().__init__(name="Chapter Drafting Agent", base_url=base_url, api_key=api_key, model=model)

    def generate_draft(self, context):
        """
        Chapter Drafting Agent：根据上下文（特别是卷纲、历史和人物线索）生成下一章的章纲。
        """
        prompt = PromptLoader.load("chapter_drafting", context=context)
        return self.generate(prompt)