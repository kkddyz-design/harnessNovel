import json
from .base_agent import BaseAgent
from core.prompt_loader import PromptLoader
from core.text_utils import parse_json_response

class SelfCheckAgent(BaseAgent):
    def __init__(self, base_url=None, api_key=None, model=None):
        super().__init__(name="Self-Check Agent", base_url=base_url, api_key=api_key, model=model)

    def check(self, draft, context, max_retries=2):
        """
        对照18项自检清单逐条检查初稿，返回违规清单(dict)。
        """
        prompt = PromptLoader.load("self_check", context=context, draft=draft)

        for attempt in range(max_retries + 1):
            result_str = self.llm.generate(prompt, is_json=True)
            try:
                result = parse_json_response(result_str)
                if "violations" in result:
                    return result
            except Exception as e:
                if attempt < max_retries:
                    print(f"[{self.name}] 自检JSON解析失败（第{attempt+1}次），重试中... 错误: {e}")
                else:
                    print(f"[{self.name}] 自检JSON解析失败，已重试{max_retries}次。")
                    return {"violations": [], "passed": 0, "failed": 0,
                            "error": f"自检输出格式异常: {result_str}"}
        return {"violations": [], "passed": 0, "failed": 0}

    def revise(self, draft, violations_dict, max_retries=1):
        """
        基于违规清单对初稿做靶向修订，返回 (修订后文本, 修订摘要)。
        """
        if not violations_dict.get("violations"):
            return draft, "无需修订"

        violations_str = json.dumps(violations_dict["violations"], ensure_ascii=False, indent=2)
        prompt = PromptLoader.load("revision", draft=draft, violations=violations_str)

        for attempt in range(max_retries + 1):
            result_str = self.llm.generate(prompt, is_json=True)
            try:
                revision = parse_json_response(result_str)
                revised_text = self._apply_revisions(draft, revision.get("revisions", []))
                summary = revision.get("summary", "")
                return revised_text, summary
            except Exception as e:
                if attempt < max_retries:
                    print(f"[{self.name}] 修订JSON解析失败（第{attempt+1}次），重试中... 错误: {e}")
                else:
                    print(f"[{self.name}] 修订JSON解析失败，返回原文。错误: {e}")
                    return draft, f"修订失败: {e}"
        return draft, "修订失败"

    @staticmethod
    def _apply_revisions(original_text, revisions):
        """
        根据 revision 指令列表，逐条对原文进行 replace/delete 修补。
        替换失败（target_text 不匹配）静默跳过。
        """
        text = original_text
        applied = 0
        for rev in revisions:
            target = rev.get("target_text", "")
            if not target:
                continue
            if target not in text:
                print(f"[Self-Check Agent] 警告：target_text 未在原文中找到，跳过。片段: {target[:50]}...")
                continue
            if rev.get("action") == "delete":
                text = text.replace(target, "", 1)
                applied += 1
            elif rev.get("action") == "replace":
                replacement = rev.get("replacement", "")
                text = text.replace(target, replacement, 1)
                applied += 1
        print(f"[Self-Check Agent] 成功应用 {applied}/{len(revisions)} 条修订指令。")
        return text
