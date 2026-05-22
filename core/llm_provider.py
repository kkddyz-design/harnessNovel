import os
from openai import OpenAI
from core.text_utils import normalize_text

# 不值得重试的 HTTP 状态码（认证/余额等确定性错误）
_NO_RETRY_CODES = {401, 402, 403}


class LLMProvider:
    def __init__(self, model="mock-model", base_url=None, api_key=None, max_tokens=None):
        self.model = model
        self.base_url = base_url
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.max_tokens = max_tokens

        if self.api_key and self.api_key != "sk-drafting-key" and self.api_key != "sk-comparison-key" and self.api_key != "sk-optimizer-key":
            self.client = OpenAI(api_key=self.api_key, base_url=self.base_url)
        else:
            self.client = None

    def generate(self, prompt, temperature=0.7, is_json=False, max_retries=2, max_tokens=None):
        """
        调用大语言模型生成内容。
        支持真实 API 调用与模拟调用（Mock）。
        API 调用失败时最多重试 max_retries 次，401/402/403 等确定性错误直接跳过重试。
        """
        print(f"[LLMProvider] 正在调用模型 {self.model} ...")

        # 真实 API 调用（带重试）
        if self.client:
            response_format = {"type": "json_object"} if is_json else None
            messages = [{"role": "user", "content": prompt}]

            kwargs = {
                "model": self.model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens or self.max_tokens,
            }
            if is_json:
                kwargs["response_format"] = response_format

            for attempt in range(max_retries + 1):
                try:
                    response = self.client.chat.completions.create(**kwargs)
                    return normalize_text(response.choices[0].message.content)
                except Exception as e:
                    status_code = getattr(e, 'status_code', None)
                    # 确定性错误不重试
                    if status_code in _NO_RETRY_CODES:
                        print(f"[LLMProvider] API 错误 ({status_code})，不可重试，回退到 Mock 模式。")
                        break
                    if attempt < max_retries:
                        print(f"[LLMProvider] API 调用失败（第{attempt+1}次），重试中... 错误: {e}")
                    else:
                        print(f"[LLMProvider] API 调用失败，已重试{max_retries}次，回退到 Mock 模式。错误: {e}")

        # 简单模拟返回内容
        if "Optimizer Agent" in prompt:
            return normalize_text("已提取优化规则：\n1. 伏笔回收需要增加至少两段的铺垫过渡。\n2. 人物对话时需加入更多神态和动作描写以体现关系。")
        elif "Comparison Agent" in prompt:
            return normalize_text("【审计结果】初稿基本符合预期，但对于部分伏笔的回收不够自然，人物互动可以更深入。建议在 AGENTS.md 中增加关于伏笔回收应平滑过渡的规则。")
        elif "Drafting Agent" in prompt:
            return normalize_text("【第一章 初入江湖】\n风起云涌，剑气如霜。主角李逍遥走在街头，想起了从前的种种。这是一个动荡的时代，但他并不害怕……")
        else:
            if is_json:
                return normalize_text('{"clues": "新增伏笔...", "characters": "人物状态更新...", "dynamic_worldview": "世界观补充...", "plot_summary": "剧情摘要..."}')
            return "LLM生成的通用回复内容。"
