import os
from openai import OpenAI
from core.text_utils import normalize_text
from core.exceptions import ImportInterrupted
from log.logger import get_logger

_NO_RETRY_CODES = {401, 402, 403}


class LLMProvider:
    def __init__(self, model=None, base_url=None, api_key=None, max_tokens=None):
        self.model = model
        self.base_url = base_url
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.max_tokens = max_tokens
        self.log = get_logger()
        self._mock = (self.api_key == "mock" or model == "mock")

        if self._mock:
            self.log.info(f"LLMProvider：Mock 模式启用（model={model}），返回模拟数据用于测试。")
            self.client = None
        elif self.api_key:
            suffix = self.api_key[-4:] if len(self.api_key) >= 4 else "****"
            self.log.info(f"LLMProvider 初始化：model={model}, base_url={base_url}, api_key=***{suffix}")
            self.client = OpenAI(api_key=self.api_key, base_url=self.base_url)
        else:
            self.log.info(f"LLMProvider：未配置 api_key，将无法调用 API（model={model}）")
            self.client = None

    def generate(self, prompt, temperature=0.7, is_json=False, max_retries=2, max_tokens=None):
        self.log.info(f"LLMProvider.generate() model={self.model} temp={temperature} json={is_json}")

        if self._mock:
            self.log.info(f"LLMProvider.generate() MOCK — returning placeholder content")
            if is_json:
                return '{"message": "Mock 响应 — 未配置真实 API Key。请设置后重试。"}'
            return "（Mock 响应 — 未配置真实 API Key。请在配置页面设置 API Key 后重试。）"

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

    def generate_interruptible(self, prompt, stop_event, temperature=0.7, max_tokens=None):
        """流式生成，chunk 间检查 stop_event，支持用户随时中断。
        流式失败时自动降级为非流式调用。
        """
        self.log.info(f"LLMProvider.generate_interruptible() model={self.model} temp={temperature}")

        if self._mock:
            self.log.info(f"LLMProvider.generate_interruptible() MOCK")
            return "（Mock 响应 — 未配置真实 API Key。请在配置页面设置 API Key 后重试。）"

        if not self.client:
            raise RuntimeError("未配置有效的 API Key，无法调用 LLM。请在配置页面设置 API Key。")

        if stop_event and stop_event.is_set():
            raise ImportInterrupted("导入已被用户停止")

        kwargs = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature,
            "max_tokens": max_tokens or self.max_tokens,
            "stream": True,
        }
        try:
            kwargs["stream_options"] = {"include_usage": True}
        except Exception:
            pass

        self.log.llm_request(self.model, self.base_url, prompt)

        last_error = None
        for attempt in range(3):
            try:
                stream = self.client.chat.completions.create(**kwargs)
                chunks = []
                for chunk in stream:
                    if stop_event and stop_event.is_set():
                        self.log.info("generate_interruptible: stop_event 触发，中止请求")
                        stream.close()
                        raise ImportInterrupted("导入已被用户停止")
                    if chunk.choices and chunk.choices[0].delta.content:
                        chunks.append(chunk.choices[0].delta.content)

                content = "".join(chunks)
                if not content:
                    raise RuntimeError("流式返回为空，可能提供方不支持 streaming")
                self.log.llm_response(
                    self.model,
                    content[:300] + ("..." if len(content) > 300 else ""),
                    full_response=content,
                )
                self.log.success(f"API 调用成功 ({self.model}, stream)")
                return normalize_text(content)

            except ImportInterrupted:
                raise
            except Exception as e:
                last_error = e
                status_code = getattr(e, 'status_code', None)
                self.log.error(f"流式 API 调用失败 (attempt {attempt+1}): status={status_code}, error={e}")
                if status_code in _NO_RETRY_CODES:
                    break
                if attempt < 2:
                    self.log.info(f"重试中... ({attempt+1}/2)")

        # 流式全部失败，降级为非流式调用
        self.log.info("流式调用失败，降级为非流式 generate()")
        return self.generate(prompt, temperature=temperature, max_tokens=max_tokens)
