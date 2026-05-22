import os
from .base_agent import BaseAgent

class PersistentAgent(BaseAgent):
    def __init__(self, base_dir="file_system"):
        # Persistent Agent doesn't strictly need LLM, but we inherit for consistency if needed later
        super().__init__(name="Persistent Agent")
        self.base_dir = base_dir

    def save_chapter(self, chapter_title, content):
        """
        Persistent Agent：定稿后更新文件系统
        1. 保存生成的章节内容
        2. (可选) 更新人物档案、前文总结等
        """
        print(f"[{self.name}] 正在持久化章节：{chapter_title}...")
        chapters_dir = os.path.join(self.base_dir, "history", "chapters")
        os.makedirs(chapters_dir, exist_ok=True)
        
        # 简单计算下一个章节编号
        existing_chapters = os.listdir(chapters_dir)
        next_idx = len(existing_chapters) + 1
        filename = f"{next_idx:03d}_{chapter_title}.md"
        filepath = os.path.join(chapters_dir, filename)
        
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(f"# {chapter_title}\n\n{content}\n")
            
        print(f"[{self.name}] 章节已保存至：{filepath}")
        return filepath
