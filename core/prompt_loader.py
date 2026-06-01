import os
import string


class PromptLoader:
    _prompts = {}
    _base_dir = os.path.join(os.path.dirname(__file__), "prompts")

    @classmethod
    def load(cls, folder_name: str, **kwargs) -> str:
        if folder_name not in cls._prompts:
            file_path = os.path.join(cls._base_dir, folder_name, "prompt.txt")
            if not os.path.exists(file_path):
                raise FileNotFoundError(f"Prompt template file not found: {file_path}")
            with open(file_path, "r", encoding="utf-8") as f:
                cls._prompts[folder_name] = f.read()

        template = cls._prompts[folder_name]
        try:
            return template.format(**kwargs)
        except KeyError as e:
            raise KeyError(
                f"Missing required parameter {e} for prompt '{folder_name}'. "
                f"Template expects keys: {cls._extract_keys(template)}"
            )
        except ValueError as e:
            raise ValueError(
                f"Format error in prompt '{folder_name}': {e}. "
                "Template may contain literal '{' or '}' — use '{{' and '}}' to escape."
            )

    @classmethod
    def _extract_keys(cls, template: str) -> list:
        """Extract all {key} placeholders from a template string."""
        formatter = string.Formatter()
        return [f[1] for f in formatter.parse(template) if f[1]]

    @classmethod
    def validate(cls, folder_name: str) -> list:
        """Validate a prompt template returns missing keys or empty list if OK."""
        file_path = os.path.join(cls._base_dir, folder_name, "prompt.txt")
        if not os.path.exists(file_path):
            return [f"Template not found: {file_path}"]
        with open(file_path, "r", encoding="utf-8") as f:
            template = f.read()
        cls._prompts[folder_name] = template
        return []  # Template loaded successfully; keys validated at format time
