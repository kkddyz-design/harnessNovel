import os
from openai import OpenAI
from core.text_utils import normalize_text
from log.logger import get_logger

# 不值得重试的 HTTP 状态码（认证/余额等确定性错误）
_NO_RETRY_CODES = {401, 402, 403}


class LLMProvider:
    def __init__(self, model="mock-model", base_url=None, api_key=None, max_tokens=None):
        self.model = model
        self.base_url = base_url
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.max_tokens = max_tokens
        self.log = get_logger()

        _mock_keys = {"", "sk-drafting-key", "sk-comparison-key", "sk-optimizer-key", "your-api-key"}
        if self.api_key and self.api_key not in _mock_keys:
            self.log.info(f"LLMProvider 初始化：model={model}, base_url={base_url}, api_key=***{self.api_key[-4:]}")
            self.client = OpenAI(api_key=self.api_key, base_url=self.base_url)
        else:
            self.log.info(f"LLMProvider Mock 模式：model={model}, api_key 为空或为占位符")
            self.client = None

    def generate(self, prompt, temperature=0.7, is_json=False, max_retries=2, max_tokens=None):
        """
        调用大语言模型生成内容。
        支持真实 API 调用与模拟调用（Mock）。
        API 调用失败时最多重试 max_retries 次，401/402/403 等确定性错误直接跳过重试。
        """
        self.log.info(f"LLMProvider.generate() model={self.model} temp={temperature} json={is_json}")

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

            self.log.llm_request(self.model, self.base_url, prompt)

            for attempt in range(max_retries + 1):
                try:
                    response = self.client.chat.completions.create(**kwargs)
                    content = response.choices[0].message.content
                    usage = getattr(response, "usage", None)
                    if usage:
                        self.log.llm_response(
                            self.model, content[:300] + ("..." if len(content) > 300 else ""),
                            full_response=content,
                            detail=f"tokens: prompt={usage.prompt_tokens}, completion={usage.completion_tokens}",
                        )
                    else:
                        self.log.llm_response(self.model, content[:300] + ("..." if len(content) > 300 else ""),
                                              full_response=content)
                    self.log.success(f"API 调用成功 ({self.model})")
                    return normalize_text(content)
                except Exception as e:
                    status_code = getattr(e, 'status_code', None)
                    self.log.error(f"API 调用失败 (attempt {attempt+1}): status={status_code}, error={e}")
                    if status_code in _NO_RETRY_CODES:
                        self.log.error(f"确定性错误 {status_code}，停止重试")
                        break
                    if attempt < max_retries:
                        self.log.info(f"重试中... ({attempt+1}/{max_retries})")
                    else:
                        self.log.error(f"已达最大重试次数 {max_retries}")

        # Mock 回退
        self.log.info("使用 Mock 模式返回")
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
