from .drafting_agent import DraftingAgent

class ChapterDraftingAgent(DraftingAgent):
    def __init__(self, base_url=None, api_key=None, model=None):
        super().__init__(name="Chapter Drafting Agent", base_url=base_url, api_key=api_key,
                         model=model, prompt_folder="chapter_drafting")
