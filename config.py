import os
from dotenv import load_dotenv

# 加载环境变量（override=True 强制覆盖已存在的环境变量）
load_dotenv(override=True)


def normalize_openai_compatible_base_url(url: str) -> str:
    """
    规范化 OpenAI 兼容 API 的 base URL。
    官方与多数中转（如 New API / One API 类）均在 /v1 下提供 /chat/completions；
    若只填域名（如 https://cc.580ai.net），OpenAI SDK 可能请求错误路径并解析异常。
    """
    default = "https://api.deepseek.com/v1"
    if not url or not str(url).strip():
        return default
    u = str(url).strip().rstrip("/")
    if u.lower().endswith("/v1"):
        return u
    # 路径里已有 /v1 片段时不重复追加（避免误伤自定义路径）
    rest = u.split("://", 1)[-1]
    if "/v1" in rest:
        return u
    return u + "/v1"


# DeepSeek API配置
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = normalize_openai_compatible_base_url(
    os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
)

# 默认AI模型名称（支持任何OpenAI兼容的模型）
DEFAULT_MODEL_NAME = os.getenv("DEFAULT_MODEL_NAME", "deepseek-chat")

# 其他配置
TUSHARE_TOKEN = os.getenv("TUSHARE_TOKEN", "")

# 股票数据源配置
DEFAULT_PERIOD = "1y"  # 默认获取1年数据
DEFAULT_INTERVAL = "1d"  # 默认日线数据

# MiniQMT量化交易配置
MINIQMT_CONFIG = {
    'enabled': os.getenv("MINIQMT_ENABLED", "false").lower() == "true",
    'account_id': os.getenv("MINIQMT_ACCOUNT_ID", ""),
    'host': os.getenv("MINIQMT_HOST", "127.0.0.1"),
    'port': int(os.getenv("MINIQMT_PORT", "58610")),
}

# TDX股票数据API配置项目地址github.com/oficcejo/tdx-api
TDX_CONFIG = {
    'enabled': os.getenv("TDX_ENABLED", "false").lower() == "true",
    'base_url': os.getenv("TDX_BASE_URL", "http://192.168.1.222:8181"),
}