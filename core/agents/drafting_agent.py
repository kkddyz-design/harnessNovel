from .base_agent import BaseAgent
from core.prompt_loader import PromptLoader

class DraftingAgent(BaseAgent):
    def __init__(self, base_url=None, api_key=None, model=None, prompt_folder="drafting"):
        super().__init__(name="Drafting Agent", base_url=base_url, api_key=api_key, model=model)
        self.prompt_folder = prompt_folder

    def generate_draft(self, context):
        prompt = PromptLoader.load(self.prompt_folder, context=context)
        return self.generate(prompt)
