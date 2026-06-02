"""
日志模块：统一记录系统运行日志
包含：LLM 请求/响应日志、系统事件、错误信息、成功提示等
支持线程安全写入文件 + 内存缓存最近日志供 GUI 实时展示
"""

import os
import json
import threading
from datetime import datetime

# 日志存储根目录：用户目录下 .harnessNovel/logs
_LOG_DIR = os.path.join(os.path.expanduser("~"), ".harnessNovel", "logs")
# 自动创建日志目录，不存在则创建，存在则忽略
os.makedirs(_LOG_DIR, exist_ok=True)


def _today_log_path():
    """
    生成今日日志文件路径
    按日期分割日志文件：每天一个独立日志文件
    返回格式：~/.harnessNovel/logs/YYYY-MM-DD.log
    """
    today = datetime.now().strftime("%Y-%m-%d")
    return os.path.join(_LOG_DIR, f"{today}.log")


class LogManager:
    """
    线程安全的单例日志管理器
    核心功能：
    1. 内存缓存最近500条日志，用于GUI快速展示
    2. 线程安全写入日志文件，避免多线程冲突
    3. 提供分级日志接口：info/success/error/LLM请求响应专用日志
    """

    # 单例实例，保证全局只有一个日志管理器
    _instance = None
    # 线程锁：保证单例创建线程安全
    _lock = threading.Lock()

    def __new__(cls):
        """
        重写__new__实现单例模式
        双重检查锁：保证多线程下只创建一个实例
        """
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    # 初始化实例属性
                    cls._instance._init()
        return cls._instance

    def _init(self):
        """
        日志管理器初始化（仅在第一次创建实例时执行）
        初始化内存日志缓冲区、文件写入锁
        """
        self._buffer = []  # 内存日志缓冲区：仅保留最近 500 条
        self._file_lock = threading.Lock()  # 文件写入锁：防止多线程同时写文件

    # ────────────────── 公共日志 API ──────────────────

    def log(self, level, message, detail=None, raw_bytes=None):
        """
        基础日志记录方法（所有日志的底层实现）
        :param level: 日志级别（INFO/SUCCESS/ERROR/LLM_REQ/LLM_RESP）
        :param message: 日志主信息（简短描述）
        :param detail: 详细信息（可选，如完整请求、响应内容）
        :param raw_bytes: 原始字节数据（可选，仅记录前200字节预览）
        """
        # 构建标准日志结构（时间戳+级别+信息）
        entry = {
            "ts": datetime.now().strftime("%H:%M:%S.%f")[:-3],  # 时间戳：时:分:秒.毫秒
            "level": level,
            "message": message,
        }
        # 可选字段：详细信息
        if detail:
            entry["detail"] = detail
        # 可选字段：原始字节预览（避免日志过大）
        if raw_bytes is not None:
            entry["raw_bytes_preview"] = str(raw_bytes[:200])

        # 线程安全写入内存缓冲区
        with self._lock:
            self._buffer.append(entry)
            # 限制缓冲区最大500条，保留最新记录
            if len(self._buffer) > 500:
                self._buffer = self._buffer[-500:]

        # 异步写入日志文件
        self._write_file(entry)

    def info(self, message, **kw):
        """普通系统信息日志（同时打印控制台）"""
        self.log("INFO", message, **kw)
        print(message)

    def success(self, message, **kw):
        """操作成功日志（同时打印控制台）"""
        self.log("SUCCESS", message, **kw)
        print(message)

    def error(self, message, **kw):
        """错误信息日志（同时打印控制台）"""
        self.log("ERROR", message, **kw)
        print(message)

    def llm_request(self, model, base_url, prompt_preview, **kw):
        """
        LLM 请求专用日志
        :param model: 使用的模型名称
        :param base_url: 请求的接口地址
        :param prompt_preview: 请求提示词预览（仅记录前500字符）
        """
        self.log("LLM_REQ", f"→ {model} @ {base_url}", detail=prompt_preview[:500], **kw)

    def llm_response(self, model, response_preview, full_response=None, **kw):
        """
        LLM 响应专用日志
        :param model: 使用的模型名称
        :param response_preview: 响应内容预览
        :param full_response: 完整响应内容（用于统计长度）
        """
        self.log(
            "LLM_RESP",
            f"← {model} ({len(full_response or response_preview)} chars)",
            detail=response_preview[:500],
            **kw,
        )

    # ────────────────── 日志文件写入 ──────────────────

    def _write_file(self, entry):
        """
        线程安全将日志写入今日日志文件
        捕获异常：写入失败（磁盘满、权限不足）不影响主程序运行
        """
        with self._file_lock:
            try:
                path = _today_log_path()
                # JSON格式写入，保证中文正常显示
                line = json.dumps(entry, ensure_ascii=False) + "\n"
                with open(path, "a", encoding="utf-8") as f:
                    f.write(line)
            except Exception:
                # 日志写入失败为非致命错误，直接忽略即可
                pass

    # ────────────────── GUI 界面展示接口 ──────────────────

    def get_recent(self, n=100, level=None):
        """
        获取最近N条内存日志（供GUI展示）
        :param n: 获取条数，默认100条
        :param level: 按日志级别过滤，None=返回全部
        :return: 日志列表
        """
        with self._lock:
            entries = list(self._buffer[-n:])
        # 按级别筛选
        if level:
            entries = [e for e in entries if e["level"] == level]
        return entries

    def get_all_text(self, n=200):
        """
        获取最近N条日志的纯文本格式（直接用于GUI文本框显示）
        包含图标+时间+信息，格式简洁直观
        """
        entries = self.get_recent(n)
        lines = []
        # 日志级别对应图标
        icon = {"INFO": "·", "SUCCESS": "✓", "ERROR": "✗", "LLM_REQ": "→", "LLM_RESP": "←"}
        for e in entries:
            lines.append(f"[{e['ts']}] {icon.get(e['level'], '·')} {e['message']}")
        return "\n".join(lines)

    def clear(self):
        """清空内存日志缓冲区（用于GUI清空日志操作）"""
        with self._lock:
            self._buffer.clear()


def get_logger():
    """获取全局唯一的日志管理器实例（对外入口函数）"""
    return LogManager()