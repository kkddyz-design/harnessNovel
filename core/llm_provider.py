import os
from openai import OpenAI
from core.text_utils import normalize_text
from log.logger import get_logger

_NO_RETRY_CODES = {401, 402, 403}


class LLMProvider:
    def __init__(self, model=None, base_url=None, api_key=None, max_tokens=None):
        self.model = model
        self.base_url = base_url
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.max_tokens = max_tokens
        self.log = get_logger()

        if self.api_key:
            self.log.info(f"LLMProvider 初始化：model={model}, base_url={base_url}, api_key=***{self.api_key[-4:]}")
            self.client = OpenAI(api_key=self.api_key, base_url=self.base_url)
        else:
            self.log.info(f"LLMProvider：未配置 api_key，将无法调用 API（model={model}）")
            self.client = None

    def generate(self, prompt, temperature=0.7, is_json=False, max_retries=2, max_tokens=None):
        self.log.info(f"LLMProvider.generate() model={self.model} temp={temperature} json={is_json}")

        if not self.client:
            raise RuntimeError("未配置有效的 API Key，无法调用 LLM。请在配置页面设置 API Key。")

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

        # API 调用重试循环（仅处理网络/服务端错误，日志错误不触发重试）
        last_error = None
        response = None
        for attempt in range(max_retries + 1):
            try:
                response = self.client.chat.completions.create(**kwargs)
                break
            except Exception as e:
                last_error = e
                status_code = getattr(e, 'status_code', None)
                self.log.error(f"API 调用失败 (attempt {attempt+1}): status={status_code}, error={e}")
                if status_code in _NO_RETRY_CODES:
                    self.log.error(f"确定性错误 {status_code}，停止重试")
                    break
                if attempt < max_retries:
                    self.log.info(f"重试中... ({attempt+1}/{max_retries})")
                else:
                    self.log.error(f"已达最大重试次数 {max_retries}")

        if response is None:
            raise last_error or RuntimeError("API 调用失败")

        content = response.choices[0].message.content
        usage = getattr(response, "usage", None)

        # 记录响应日志
        self.log.llm_response(
            self.model,
            content[:300] + ("..." if len(content) > 300 else ""),
            full_response=content,
        )
        if usage:
            self.log.info(
                f"token 用量：prompt={usage.prompt_tokens}, completion={usage.completion_tokens}"
            )
        self.log.success(f"API 调用成功 ({self.model})")
        return normalize_text(content)
