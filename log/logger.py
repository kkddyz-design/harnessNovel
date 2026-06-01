"""日志模块：记录 LLM 请求/响应、错误、系统事件。"""

import os
import json
import threading
from datetime import datetime

_LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)))


def _today_log_path():
    today = datetime.now().strftime("%Y-%m-%d")
    return os.path.join(_LOG_DIR, f"{today}.log")


class LogManager:
    """线程安全的日志管理器，同时写文件 + 内存保留最近 N 条供 GUI 展示。"""

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._init()
        return cls._instance

    def _init(self):
        self._buffer = []  # 内存日志（最近 500 条）
        self._file_lock = threading.Lock()

    # ── 公共 API ──

    def log(self, level, message, detail=None, raw_bytes=None):
        """记录一条日志。"""
        entry = {
            "ts": datetime.now().strftime("%H:%M:%S.%f")[:-3],
            "level": level,
            "message": message,
        }
        if detail:
            entry["detail"] = detail
        if raw_bytes is not None:
            entry["raw_bytes_preview"] = str(raw_bytes[:200])

        with self._lock:
            self._buffer.append(entry)
            if len(self._buffer) > 500:
                self._buffer = self._buffer[-500:]

        self._write_file(entry)

    def info(self, message, **kw):
        self.log("INFO", message, **kw)

    def success(self, message, **kw):
        self.log("SUCCESS", message, **kw)

    def error(self, message, **kw):
        self.log("ERROR", message, **kw)

    def llm_request(self, model, base_url, prompt_preview, **kw):
        self.log("LLM_REQ", f"→ {model} @ {base_url}", detail=prompt_preview[:500], **kw)

    def llm_response(self, model, response_preview, full_response=None, **kw):
        self.log(
            "LLM_RESP",
            f"← {model} ({len(full_response or response_preview)} chars)",
            detail=response_preview[:500],
            **kw,
        )

    # ── 文件写入 ──

    def _write_file(self, entry):
        with self._file_lock:
            try:
                path = _today_log_path()
                line = json.dumps(entry, ensure_ascii=False) + "\n"
                with open(path, "a", encoding="utf-8") as f:
                    f.write(line)
            except Exception:
                pass

    # ── GUI 集成 ──

    def get_recent(self, n=100, level=None):
        """获取最近 N 条日志（按级别过滤，None=全部）。"""
        with self._lock:
            entries = list(self._buffer[-n:])
        if level:
            entries = [e for e in entries if e["level"] == level]
        return entries

    def get_all_text(self, n=200):
        """获取最近 N 条日志的纯文本。"""
        entries = self.get_recent(n)
        lines = []
        for e in entries:
            icon = {"INFO": "·", "SUCCESS": "✓", "ERROR": "✗", "LLM_REQ": "→", "LLM_RESP": "←"}.get(
                e["level"], "·"
            )
            lines.append(f"[{e['ts']}] {icon} {e['message']}")
        return "\n".join(lines)

    def clear(self):
        """清空内存日志。"""
        with self._lock:
            self._buffer.clear()


def get_logger():
    return LogManager()
