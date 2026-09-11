import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load_env(path: Path = ROOT / ".env"):
    """极简 .env 加载：KEY=VALUE 行，# 注释，不覆盖已存在的环境变量。"""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_env()

# ---- 密钥（本地 .env 或 Actions Secrets）----
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
SERVERCHAN_SENDKEY = os.environ.get("SERVERCHAN_SENDKEY", "")
DRY_RUN = os.environ.get("DRY_RUN", "")

# ---- LLM ----
DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_MODEL = "deepseek-chat"

# ---- 信息源端点（均已实测验证）----
OPENAI_RSS_URL = "https://openai.com/news/rss.xml"
QWEN_RSS_URL = "https://qwenlm.github.io/blog/index.xml"
REDDIT_RSS_URL = "https://www.reddit.com/r/LocalLLaMA/new/.rss"
ANTHROPIC_NEWS_URL = "https://www.anthropic.com/news"
DEEPSEEK_UPDATES_URL = "https://api-docs.deepseek.com/updates/"
HF_API_BASE = "https://huggingface.co/api"
OPENROUTER_MODELS_URL = "https://openrouter.ai/api/v1/models"
HN_ALGOLIA_BASE = "https://hn.algolia.com/api/v1"
MS_SEARCH_URL = "https://modelscope.cn/api/v1/dolphin/models"

# ---- 追踪清单 ----
HF_ORGS = [
    "openai", "meta-llama", "google", "Qwen", "deepseek-ai", "mistralai",
    "moonshotai", "zai-org", "xai", "microsoft", "facebook",
]
MS_KEYWORDS = ["qwen", "deepseek", "glm", "kimi"]
# ModelScope 无 org 过滤 API：按关键词搜索后客户端过滤这些官方组织 Path
MS_ORG_MAP = {
    "qwen": {"Qwen"},
    "deepseek": {"deepseek-ai"},
    "glm": {"ZhipuAI"},
    "kimi": {"moonshotai"},
}
GH_REPOS = ["openai/gpt-oss", "meta-llama/llama-models", "google/gemma"]
HN_QUERIES = ["open weights", "model release", "open source LLM"]

USER_AGENT = "model-news-tracker/0.1 (+https://github.com/)"

# ---- 行为参数 ----
MAX_CANDIDATES_PER_JUDGE = 60  # 单轮最多送判条数，超出转 pending 下轮判
SKIP_OLDER_THAN_HOURS = 48     # 早于此的条目直接记 seen

# ---- 持久化路径 ----
STATE_PATH = ROOT / "state" / "seen.json"
EVENTS_MD_PATH = ROOT / "events.md"
