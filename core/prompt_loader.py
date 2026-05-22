import os

class PromptLoader:
    _prompts = {}
    _base_dir = os.path.join(os.path.dirname(__file__), "prompts")

    @classmethod
    def load(cls, folder_name: str, **kwargs) -> str:
        """
        加载指定 folder_name 下的 prompt.txt，并使用 kwargs 进行格式化。
        这种方式支持每一个 prompt 拥有一个独立的文件夹，方便长文本阅读与修改。
        """
        if folder_name not in cls._prompts:
            file_path = os.path.join(cls._base_dir, folder_name, "prompt.txt")
            if not os.path.exists(file_path):
                raise FileNotFoundError(f"Prompt 模板文件未找到: {file_path}")
            with open(file_path, "r", encoding="utf-8") as f:
                cls._prompts[folder_name] = f.read()
                
        template = cls._prompts[folder_name]
            
        # 使用 kwargs 格式化模板
        try:
            return template.format(**kwargs)
        except KeyError as e:
            raise KeyError(f"格式化 prompt 文件夹 '{folder_name}' 时缺少必要的参数: {e}")
