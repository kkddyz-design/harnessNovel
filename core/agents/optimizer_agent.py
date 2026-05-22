import os
import re
from .base_agent import BaseAgent
from core.prompt_loader import PromptLoader
from core.text_utils import clean_markdown_symbols, normalize_text

class OptimizerAgent(BaseAgent):
    def __init__(self, base_url=None, api_key=None, model="mock-model"):
        super().__init__(name="Optimizer Agent", base_url=base_url, api_key=api_key, model=model)

    def _read_file(self, path):
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return f.read().strip()
        return "暂无内容"

    def _write_file(self, path, content):
        content = clean_markdown_symbols(content)
        content = normalize_text(content)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)

    def _extract_xml_tag(self, text, tag):
        match = re.search(rf'<{tag}>\s*(.*?)\s*</{tag}>', text, re.DOTALL)
        return match.group(1).strip() if match else None

    def optimize_parameters(self, feedback, base_dir="file_system", prompts_dir="core/prompts", attribution="drafting_error"):
        """
        根据归因类型选择性读取和更新对应的训练参数文件。
        attribution: drafting_error / summary_error / update_error
        """
        agents_md_path = os.path.join(base_dir, "AGENTS.md")
        summary_prompt_path = os.path.join(prompts_dir, "summary", "prompt.txt")
        update_prompt_path = os.path.join(prompts_dir, "update", "prompt.txt")
        self_check_prompt_path = os.path.join(prompts_dir, "self_check", "prompt.txt")
        revision_prompt_path = os.path.join(prompts_dir, "revision", "prompt.txt")

        # 根据 attribution 构建 existing_files_section
        if attribution == "drafting_error":
            existing_files_section = (
                "【现有的 AGENTS.md】\n"
                + self._read_file(agents_md_path)
                + "\n\n【现有的自检 prompt】\n"
                + self._read_file(self_check_prompt_path)
                + "\n\n【现有的修订 prompt】\n"
                + self._read_file(revision_prompt_path)
            )
        elif attribution == "summary_error":
            existing_files_section = (
                "【现有的 summary_prompt】\n"
                + self._read_file(summary_prompt_path)
            )
        elif attribution == "update_error":
            existing_files_section = (
                "【现有的 update_prompt】\n"
                + self._read_file(update_prompt_path)
            )
        else:
            existing_files_section = "【无对应文件】"

        prompt = PromptLoader.load(
            "optimizer",
            attribution=attribution,
            existing_files_section=existing_files_section,
            feedback=feedback
        )

        optimization_result = self.generate(prompt)

        # 清理 markdown 代码块标记
        if optimization_result.startswith("```xml"):
            optimization_result = optimization_result[len("```xml"):].strip()
        elif optimization_result.startswith("```"):
            optimization_result = optimization_result[len("```"):].strip()
        if optimization_result.endswith("```"):
            optimization_result = optimization_result[:-3].strip()

        updated_files = []

        # drafting_error: 解析并写入 AGENTS.md + self_check + revision
        if attribution == "drafting_error":
            agents_md_content = self._extract_xml_tag(optimization_result, "agents_md")
            if agents_md_content:
                self._write_file(agents_md_path, agents_md_content)
                updated_files.append("AGENTS.md")

            self_check_content = self._extract_xml_tag(optimization_result, "self_check_prompt")
            if self_check_content:
                self._write_file(self_check_prompt_path, self_check_content)
                updated_files.append("self_check_prompt")

            revision_content = self._extract_xml_tag(optimization_result, "revision_prompt")
            if revision_content:
                self._write_file(revision_prompt_path, revision_content)
                updated_files.append("revision_prompt")

        # summary_error: 解析并写入 summary_prompt
        elif attribution == "summary_error":
            summary_content = self._extract_xml_tag(optimization_result, "summary_prompt")
            if summary_content:
                self._write_file(summary_prompt_path, summary_content)
                updated_files.append("summary_prompt")

        # update_error: 解析并写入 update_prompt
        elif attribution == "update_error":
            update_content = self._extract_xml_tag(optimization_result, "update_prompt")
            if update_content:
                self._write_file(update_prompt_path, update_content)
                updated_files.append("update_prompt")

        print(f"[{self.name}] 归因={attribution}, 已融合更新文件: {', '.join(updated_files) if updated_files else '无'}")
        return optimization_result
