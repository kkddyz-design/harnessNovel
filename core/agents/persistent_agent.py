import os


class PersistentAgent:
    """Persistent Agent：将章节内容持久化到文件系统。不需要 LLM。"""

    def __init__(self, base_dir="file_system"):
        self.name = "Persistent Agent"
        self.base_dir = base_dir

    def save_chapter(self, chapter_title, content):
        print(f"[{self.name}] 正在持久化章节：{chapter_title}...")
        chapters_dir = os.path.join(self.base_dir, "history", "chapters")
        os.makedirs(chapters_dir, exist_ok=True)

        existing_chapters = os.listdir(chapters_dir)
        next_idx = len(existing_chapters) + 1
        filename = f"{next_idx:03d}_{chapter_title}.md"
        filepath = os.path.join(chapters_dir, filename)

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(f"# {chapter_title}\n\n{content}\n")

        print(f"[{self.name}] 章节已保存至：{filepath}")
        return filepath
