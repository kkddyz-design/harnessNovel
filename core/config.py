import os


def _load_env(env_path=".env"):
    """读取 .env 文件为字典。"""
    env = {}
    if not os.path.exists(env_path):
        return env
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, value = line.split("=", 1)
                env[key.strip()] = value.strip()
    return env


class ConfigLoader:
    _env = None

    @classmethod
    def _get_env(cls):
        if cls._env is None:
            cls._env = _load_env()
        return cls._env

    @classmethod
    def _build_config(cls, prefix):
        """根据前缀从环境变量/.env 构建 LLM 配置字典。"""
        env = cls._get_env()
        return {
            "model": os.getenv(f"{prefix}_MODEL") or env.get(f"{prefix}_MODEL", ""),
            "base_url": os.getenv(f"{prefix}_BASE_URL") or env.get(f"{prefix}_BASE_URL", ""),
            "api_key": os.getenv(f"{prefix}_API_KEY") or env.get(f"{prefix}_API_KEY", ""),
        }

    @classmethod
    def get_data_builder_config(cls):
        """参考小说批次摘要提取的模型配置（init 流程）。"""
        return cls._build_config("DATA_BUILDER")

    @classmethod
    def get_adaptive_builder_config(cls):
        """仿写核心任务的模型配置（pro 模型）。"""
        return cls._build_config("ADAPTIVE_BUILDER")

    @classmethod
    def get_adaptive_builder_lite_config(cls):
        """仿写辅助任务的模型配置（flash 模型）。"""
        return cls._build_config("ADAPTIVE_BUILDER_LITE")
