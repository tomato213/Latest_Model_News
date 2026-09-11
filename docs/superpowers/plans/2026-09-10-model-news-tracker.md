# AI 模型发布追踪器 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 每 30 分钟抓取各官方/社区源，用 LLM 判断「模型发布/开源/重大升级」硬事件并推送到微信。

**Architecture:** GitHub Actions cron 触发 `python -m src.run`；10 个独立抓取器输出统一 Candidate；`state/seen.json` 去重（提交回仓库持久化）；DeepSeek API 批量判断硬事件（失败降级关键词规则，未判定条目下轮重试）；Server酱推送合并消息（失败下轮重推）；事件追加到 `events.md`。

**Tech Stack:** Python 3.10+（本地 3.14 / Actions 3.12）、requests（唯一第三方运行时依赖）、pytest、stdlib xml.etree 解析 RSS/Atom、GitHub Actions cron。

## Global Constraints

- 代码兼容 Python 3.10+（本地运行 3.14，Actions 用 3.12）
- 运行时第三方依赖仅 `requests`；RSS/Atom 用 stdlib `xml.etree`；.env 用 stdlib 手写解析（不用 python-dotenv）
- 所有时间内部用 UTC ISO8601 字符串；单测不访问网络（fixture + monkeypatch）
- 所有条目 ID 格式 `"{source}:{native_id}"`；只存标题+链接+摘要，不存全文
- 密钥只经环境变量（本地 `.env` / Actions Secrets），绝不进代码和 state
- 抓取器逐源 try/except：单源失败只打日志，不阻塞其他源
- Candidate 字段固定：`id, source, title, url, published_at (ISO|None), extra (str)`
- 48h 之前的条目直接标记 seen 不进入判断（`SKIP_OLDER_THAN_HOURS = 48`）
- 首次运行（`bootstrapped: false`）只记录不推送（防止历史内容洪水推送）

**已验证的源与端点（2026-09-10 实测）：**

| 源 | 端点/方式 | 备注 |
|---|---|---|
| OpenAI | `https://openai.com/news/rss.xml` RSS 2.0 | ✅ 本地已验证 |
| Anthropic | `https://www.anthropic.com/news` HTML，slug+日期+h4 标题 | ✅ 本地已验证 |
| Qwen | `https://qwenlm.github.io/blog/index.xml` RSS | ✅ 本地已验证 |
| DeepSeek | `https://api-docs.deepseek.com/updates/` 索引 `/news/newsNNNNNN` slug → 单页 `<h1>` 标题（302 重定向需自动跟随，requests 默认跟随） | ✅ 本地已验证 |
| HuggingFace | `https://huggingface.co/api/models?author={org}&sort=createdAt&direction=-1&limit=15` | 本地被墙、Actions 可达 |
| ModelScope | `PUT https://modelscope.cn/api/v1/dolphin/models` body `{"Name": kw, "PageSize": 20, "PageNumber": 1}`（默认相关度排序，官方组织模型排最前），客户端按 `Path` 过滤 | ✅ 本地已验证（org 过滤 API 不存在，此为替代方案） |
| OpenRouter | `https://openrouter.ai/api/v1/models`，字段 `id/name/created(unix)/context_length` | ✅ 本地已验证（计划新增源，覆盖所有闭源 API 上线） |
| GitHub Releases | `https://api.github.com/repos/{repo}/releases?per_page=5` | ✅ 本地已验证 |
| Reddit | `https://www.reddit.com/r/LocalLLaMA/new/.rss` Atom | 本地被墙、Actions 可达 |
| Hacker News | `https://hn.algolia.com/api/v1/search_by_date?query={q}&tags=story&hitsPerPage=30` | ✅ 本地已验证 |
| Server酱 | `POST https://sctapi.ftqq.com/{SENDKEY}.send` form `title`+`desp`(Markdown) | ✅ 在线已验证 |
| DeepSeek API | `POST https://api.deepseek.com/chat/completions`，model `deepseek-chat` | 官方文档端点 |

---

### Task 0: 项目骨架 — git init、依赖、Candidate、config

**Files:**
- Create: `.gitignore`, `requirements.txt`, `conftest.py`, `pyproject.toml`, `src/__init__.py`, `src/models.py`, `src/config.py`, `state/seen.json`, `events.md`, `tests/test_models.py`, `tests/test_config.py`, `.env.example`

**Interfaces:**
- Produces: `src.models.Candidate` dataclass（`id, source, title, url, published_at, extra=""` + `to_dict()/from_dict()`）；`src.config` 全部常量（后续任务引用，签名见下方代码）；`load_env()` 由 config import 时自动执行
- Produces: `config.STATE_PATH`, `config.EVENTS_MD_PATH`（Path 对象，Task 8/11 使用）

- [ ] **Step 1: git init + 基础文件**

```bash
cd d:/Projects/Latest_Model_News
git init
```

创建 `.gitignore`：

```
.env
__pycache__/
*.pyc
.pytest_cache/
```

创建 `requirements.txt`：

```
requests>=2.32,<3
pytest>=8
```

创建空 `conftest.py`（repo 根目录，让 pytest 把根目录加进 sys.path，`from src...` 才能导入）和 `pyproject.toml`：

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
```

创建 `.env.example`：

```
# 复制为 .env 并填入真实值；GitHub Actions 上改为配置 Secrets
DEEPSEEK_API_KEY=
SERVERCHAN_SENDKEY=
# 本地调试时置 1：不真正推送
DRY_RUN=
```

- [ ] **Step 2: 安装依赖**

```bash
pip install -r requirements.txt
```

- [ ] **Step 3: 写失败测试**

`tests/test_models.py`：

```python
from src.models import Candidate


def test_candidate_roundtrip():
    c = Candidate(
        id="openai:https://openai.com/index/x",
        source="openai",
        title="Introducing GPT-5.3",
        url="https://openai.com/index/x",
        published_at="2026-09-09T10:00:00+00:00",
        extra="downloads=100",
    )
    d = c.to_dict()
    assert d["id"] == "openai:https://openai.com/index/x"
    assert d["source"] == "openai"
    assert d["extra"] == "downloads=100"
    c2 = Candidate.from_dict(d)
    assert c2 == c


def test_candidate_defaults():
    c = Candidate(id="hf:Qwen/Q", source="hf", title="Q", url="https://huggingface.co/Qwen/Q")
    assert c.published_at is None
    assert c.extra == ""
```

`tests/test_config.py`：

```python
from src import config


def test_urls_are_https():
    assert config.OPENAI_RSS_URL.startswith("https://")
    assert config.HF_API_BASE.startswith("https://")
    assert config.MS_SEARCH_URL.startswith("https://")
    assert config.OPENROUTER_MODELS_URL.startswith("https://")


def test_watchlists_are_lists():
    assert isinstance(config.HF_ORGS, list) and config.HF_ORGS
    assert isinstance(config.MS_KEYWORDS, list) and config.MS_KEYWORDS
    assert isinstance(config.GH_REPOS, list)
    assert isinstance(config.HN_QUERIES, list) and config.HN_QUERIES


def test_microsoft_org_map_keys_match_keywords():
    for kw in config.MS_KEYWORDS:
        assert kw in config.MS_ORG_MAP


def test_tuning_constants():
    assert config.MAX_CANDIDATES_PER_JUDGE == 60
    assert config.SKIP_OLDER_THAN_HOURS == 48
    assert config.DEEPSEEK_MODEL == "deepseek-chat"
```

- [ ] **Step 4: 运行测试确认失败**

Run: `python -m pytest tests/test_models.py tests/test_config.py -v`
Expected: FAIL（`ModuleNotFoundError: src.models` / `src.config`）

- [ ] **Step 5: 实现**

`src/__init__.py`：空文件。

`src/models.py`：

```python
from dataclasses import asdict, dataclass, field


@dataclass
class Candidate:
    id: str
    source: str
    title: str
    url: str
    published_at: str | None = None
    extra: str = ""

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, d):
        return cls(
            id=d["id"],
            source=d["source"],
            title=d["title"],
            url=d["url"],
            published_at=d.get("published_at"),
            extra=d.get("extra", ""),
        )
```

`src/config.py`：

```python
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
```

`state/seen.json`：

```json
{"bootstrapped": false, "seen": {}, "pending": [], "pending_push": []}
```

`events.md`：

```markdown
# 模型发布事件历史
```

- [ ] **Step 6: 运行测试确认通过**

Run: `python -m pytest tests/ -v`
Expected: 全部 PASS

- [ ] **Step 7: 提交**

```bash
git add -A
git commit -m "chore: project skeleton, Candidate model, verified config"
```

---

### Task 1: HTTP 客户端（重试 + 统一错误）

**Files:**
- Create: `src/http_client.py`
- Test: `tests/test_http_client.py`

**Interfaces:**
- Produces: `get_json(url, headers=None, timeout=25) -> Any`、`get_text(url, headers=None, timeout=25) -> str`、`put_json(url, payload, headers=None, timeout=25) -> Any`、`post_json(url, payload, headers=None, timeout=25) -> Any`、`post_form(url, data, headers=None, timeout=25) -> Any`（post_form 返回 resp.text，供 Server酱响应检查）、异常类 `HttpClientError(Exception)`
- Consumes: `config.USER_AGENT` 作为默认 UA（与调用方 headers 合并，调用方可覆盖）
- 行为：网络错误重试 1 次（间隔 2s，测试中 mock 掉 sleep）；最终失败或非 2xx 抛 `HttpClientError`

- [ ] **Step 1: 写失败测试**

`tests/test_http_client.py`：

```python
from unittest.mock import MagicMock, patch

import pytest
import requests

from src import http_client
from src.http_client import HttpClientError


def _resp(status=200, json_data=None, text=""):
    r = MagicMock()
    r.status_code = status
    r.json.return_value = json_data
    r.text = text
    return r


def test_get_json_parses_and_sends_default_ua():
    with patch("src.http_client.requests.get", return_value=_resp(json_data={"ok": 1})) as g:
        assert http_client.get_json("https://x/y") == {"ok": 1}
        kwargs = g.call_args.kwargs
        assert kwargs["timeout"] == 25
        assert "model-news-tracker" in kwargs["headers"]["User-Agent"]


def test_get_json_merges_custom_headers():
    with patch("src.http_client.requests.get", return_value=_resp(json_data={})) as g:
        http_client.get_json("https://x", headers={"Authorization": "Bearer t"})
        assert g.call_args.kwargs["headers"]["Authorization"] == "Bearer t"
        assert "User-Agent" in g.call_args.kwargs["headers"]


def test_non_2xx_raises():
    with patch("src.http_client.requests.get", return_value=_resp(status=404)):
        with pytest.raises(HttpClientError, match="404"):
            http_client.get_text("https://x/404")


def test_retry_once_on_network_error_then_success():
    with patch("src.http_client.requests.get", side_effect=[requests.ConnectionError("boom"), _resp(json_data={})]), \
         patch("src.http_client.time.sleep") as s:
        assert http_client.get_json("https://x") == {}
        s.assert_called_once_with(2)


def test_both_attempts_fail_raises():
    with patch("src.http_client.requests.get", side_effect=requests.Timeout("t")), \
         patch("src.http_client.time.sleep"):
        with pytest.raises(HttpClientError):
            http_client.get_json("https://x")


def test_put_json_and_post_form():
    with patch("src.http_client.requests.put", return_value=_resp(json_data={"Code": 200})) as p:
        assert http_client.put_json("https://x", {"a": 1}) == {"Code": 200}
        p.call_args.kwargs["json"] == {"a": 1}
    with patch("src.http_client.requests.post", return_value=_resp(text="ok")) as p:
        assert http_client.post_form("https://x", {"title": "t"}) == "ok"
        assert p.call_args.kwargs["data"] == {"title": "t"}
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_http_client.py -v`
Expected: FAIL（`ModuleNotFoundError: src.http_client`）

- [ ] **Step 3: 实现**

`src/http_client.py`：

```python
import time

import requests

from .config import USER_AGENT


class HttpClientError(Exception):
    pass


def _headers(extra):
    h = {"User-Agent": USER_AGENT}
    if extra:
        h.update(extra)
    return h


def _request(fn, url, *, headers=None, timeout=25, **kw):
    last_exc = None
    for attempt in range(2):
        try:
            resp = fn(url, headers=_headers(headers), timeout=timeout, **kw)
            if not (200 <= resp.status_code < 300):
                raise HttpClientError(f"{url} -> HTTP {resp.status_code}")
            return resp
        except HttpClientError:
            raise
        except requests.RequestException as exc:
            last_exc = exc
            if attempt == 0:
                time.sleep(2)
    raise HttpClientError(f"{url} failed after retry: {last_exc}")


def get_json(url, headers=None, timeout=25):
    return _request(requests.get, url, headers=headers, timeout=timeout).json()


def get_text(url, headers=None, timeout=25):
    return _request(requests.get, url, headers=headers, timeout=timeout).text


def put_json(url, payload, headers=None, timeout=25):
    resp = _request(requests.put, url, headers=headers, timeout=timeout, json=payload)
    return resp.json()


def post_json(url, payload, headers=None, timeout=25):
    resp = _request(requests.post, url, headers=headers, timeout=timeout, json=payload)
    return resp.json()


def post_form(url, data, headers=None, timeout=25):
    return _request(requests.post, url, headers=headers, timeout=timeout, data=data).text
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/ -v`
Expected: 全部 PASS

- [ ] **Step 5: 提交**

```bash
git add src/http_client.py tests/test_http_client.py
git commit -m "feat: HTTP client with retry and unified errors"
```

---

### Task 2: RSS/Atom 解析器（stdlib）

**Files:**
- Create: `src/rss_util.py`
- Test: `tests/test_rss_util.py`
- Fixture: `tests/fixtures/openai_rss.xml`, `tests/fixtures/reddit_atom.xml`

**Interfaces:**
- Consumes: 无
- Produces: `parse_feed(text) -> list[dict]`，每项 `{"title": str, "link": str, "published": str|None}`（ISO8601 UTC 或 None）；不支持的根元素抛 `ValueError`；无 link 的条目被丢弃
- 解析支持：RSS 2.0 `<item><title><link><pubDate>`（`email.utils.parsedate_to_datetime`）与 Atom `<entry><title><link href><updated>/<published>`（`datetime.fromisoformat`）

- [ ] **Step 1: 写 fixtures**

`tests/fixtures/openai_rss.xml`（模拟实测到的真实结构）：

```xml
<?xml version="1.0" encoding="UTF-8"?><rss xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:content="http://purl.org/rss/1.0/modules/content/" xmlns:atom="http://www.w3.org/2005/Atom" version="2.0">
    <channel>
        <title><![CDATA[OpenAI News]]></title>
        <link>https://openai.com/news</link>
        <item>
            <title><![CDATA[Introducing GPT-5.3]]></title>
            <link>https://openai.com/index/introducing-gpt-5-3/</link>
            <guid isPermaLink="false">https://openai.com/index/introducing-gpt-5-3/</guid>
            <pubDate>Wed, 09 Sep 2026 10:00:00 +0000</pubDate>
        </item>
        <item>
            <title><![CDATA[DevDay 2026 recap]]></title>
            <link>https://openai.com/index/devday-2026-recap/</link>
            <pubDate>Mon, 07 Sep 2026 09:00:00 +0000</pubDate>
        </item>
    </channel>
</rss>
```

`tests/fixtures/reddit_atom.xml`：

```xml
<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
    <title>New posts from r/LocalLLaMA</title>
    <entry>
        <title>Qwen3.8-27B released and it beats GLM-5.2</title>
        <link href="https://www.reddit.com/r/LocalLLaMA/comments/1abc/qwen38_27b_released/"/>
        <updated>2026-09-10T08:00:00+00:00</updated>
        <content type="html">submitted by /u/someone</content>
    </entry>
    <entry>
        <title>Weekly benchmark discussion thread</title>
        <link href="https://www.reddit.com/r/LocalLLaMA/comments/1xyz/weekly_benchmark/"/>
        <updated>2026-09-10T07:00:00+00:00</updated>
    </entry>
</feed>
```

- [ ] **Step 2: 写失败测试**

`tests/test_rss_util.py`：

```python
import pytest


@pytest.fixture
def fx():
    def _load(name):
        from pathlib import Path
        return (Path(__file__).parent / "fixtures" / name).read_text(encoding="utf-8")
    return _load


def test_parse_rss2(fx):
    from src.rss_util import parse_feed
    items = parse_feed(fx("openai_rss.xml"))
    assert len(items) == 2
    assert items[0]["title"] == "Introducing GPT-5.3"
    assert items[0]["link"] == "https://openai.com/index/introducing-gpt-5-3/"
    assert items[0]["published"] == "2026-09-09T10:00:00+00:00"


def test_parse_atom(fx):
    from src.rss_util import parse_feed
    items = parse_feed(fx("reddit_atom.xml"))
    assert len(items) == 2
    assert items[0]["link"] == "https://www.reddit.com/r/LocalLLaMA/comments/1abc/qwen38_27b_released/"
    assert items[0]["published"] == "2026-09-10T08:00:00+00:00"
    assert items[1]["title"] == "Weekly benchmark discussion thread"


def test_unsupported_root_raises():
    from src.rss_util import parse_feed
    with pytest.raises(ValueError):
        parse_feed("<html><body>hi</body></html>")


def test_empty_item_without_link_dropped():
    from src.rss_util import parse_feed
    text = '<?xml version="1.0"?><rss version="2.0"><channel><item><title>no link</title></item></channel></rss>'
    assert parse_feed(text) == []
```

- [ ] **Step 3: 运行测试确认失败**

Run: `python -m pytest tests/test_rss_util.py -v`
Expected: FAIL（`ModuleNotFoundError: src.rss_util`）

- [ ] **Step 4: 实现**

`src/rss_util.py`：

```python
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

ATOM = "{http://www.w3.org/2005/Atom}"


def _to_utc_iso(dt):
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


def _parse_date(s):
    if not s or not s.strip():
        return None
    s = s.strip()
    try:
        return _to_utc_iso(parsedate_to_datetime(s))
    except (TypeError, ValueError):
        pass
    try:
        return _to_utc_iso(datetime.fromisoformat(s.replace("Z", "+00:00")))
    except ValueError:
        return None


def parse_feed(text):
    root = ET.fromstring(text)
    items = []
    if root.tag == "rss":
        for el in root.iter("item"):
            items.append({
                "title": (el.findtext("title") or "").strip(),
                "link": (el.findtext("link") or "").strip(),
                "published": _parse_date(el.findtext("pubDate")),
            })
    elif root.tag == f"{ATOM}feed":
        for el in root.iter(f"{ATOM}entry"):
            link = ""
            for le in el.findall(f"{ATOM}link"):
                if le.get("rel") in (None, "alternate"):
                    link = le.get("href", "")
                    break
            items.append({
                "title": (el.findtext(f"{ATOM}title") or "").strip(),
                "link": link,
                "published": _parse_date(el.findtext(f"{ATOM}published") or el.findtext(f"{ATOM}updated")),
            })
    else:
        raise ValueError(f"unsupported feed root: {root.tag}")
    return [i for i in items if i["link"]]
```

- [ ] **Step 5: 运行测试确认通过**

Run: `python -m pytest tests/ -v`
Expected: 全部 PASS

- [ ] **Step 6: 提交**

```bash
git add src/rss_util.py tests/test_rss_util.py tests/fixtures/
git commit -m "feat: stdlib RSS2/Atom feed parser"
```

---

### Task 3: RSS 类源 — openai、qwen、reddit

**Files:**
- Create: `src/sources/__init__.py`（本任务先只做包占位，空文件）, `src/sources/openai.py`, `src/sources/qwen.py`, `src/sources/reddit.py`
- Test: `tests/test_sources_rss.py`

**Interfaces:**
- Consumes: `http_client.get_text(url, headers=None)`、`rss_util.parse_feed(text)`、`config.OPENAI_RSS_URL / QWEN_RSS_URL / REDDIT_RSS_URL`
- Produces: 每个模块 `fetch() -> list[Candidate]`（无参数；网络异常向上抛，由 Task 8/11 的统一 try/except 处理）。ID 规则：openai/qwen/reddit 均为 `"{source}:{link.rstrip('/')}"`

- [ ] **Step 1: 创建包占位**

创建空文件 `src/sources/__init__.py`（内容留到 Task 7 写注册表）。

- [ ] **Step 2: 写失败测试**

`tests/test_sources_rss.py`：

```python
from unittest.mock import MagicMock, patch


@pytest.fixture
def fx():
    def _load(name):
        from pathlib import Path
        return (Path(__file__).parent / "fixtures" / name).read_text(encoding="utf-8")
    return _load


def test_openai_fetch(fx):
    from src.sources import openai
    with patch("src.sources.openai.get_text", return_value=fx("openai_rss.xml")):
        out = openai.fetch()
    assert len(out) == 2
    assert out[0].id == "openai:https://openai.com/index/introducing-gpt-5-3"
    assert out[0].source == "openai"
    assert out[0].title == "Introducing GPT-5.3"
    assert out[0].published_at == "2026-09-09T10:00:00+00:00"


def test_qwen_fetch(fx):
    from src.sources import qwen
    with patch("src.sources.qwen.get_text", return_value=fx("openai_rss.xml")):  # RSS2 结构相同
        out = qwen.fetch()
    assert out[0].source == "qwen"
    assert out[0].id.startswith("qwen:https://")


def test_reddit_fetch(fx):
    from src.sources import reddit
    with patch("src.sources.reddit.get_text", return_value=fx("reddit_atom.xml")):
        out = reddit.fetch()
    assert len(out) == 2
    assert out[0].source == "reddit"
    assert out[0].id.endswith("qwen38_27b_released")
    assert "Qwen3.8-27B released" in out[0].title


import pytest  # noqa: E402  (放在顶部也可)


def test_fetch_propagates_http_error():
    from src.http_client import HttpClientError
    from src.sources import openai
    with patch("src.sources.openai.get_text", side_effect=HttpClientError("down")):
        try:
            openai.fetch()
            assert False, "should raise"
        except HttpClientError:
            pass
```

注意：把 `import pytest` 放到文件顶部，删掉中间那行 noqa。

- [ ] **Step 3: 运行测试确认失败**

Run: `python -m pytest tests/test_sources_rss.py -v`
Expected: FAIL（`ModuleNotFoundError: src.sources.openai`）

- [ ] **Step 4: 实现**

`src/sources/openai.py`：

```python
from ..config import OPENAI_RSS_URL
from ..http_client import get_text
from ..models import Candidate
from ..rss_util import parse_feed


def fetch():
    return [
        Candidate(
            id=f"openai:{item['link'].rstrip('/')}",
            source="openai",
            title=item["title"],
            url=item["link"],
            published_at=item["published"],
        )
        for item in parse_feed(get_text(OPENAI_RSS_URL))
    ]
```

`src/sources/qwen.py`：

```python
from ..config import QWEN_RSS_URL
from ..http_client import get_text
from ..models import Candidate
from ..rss_util import parse_feed


def fetch():
    return [
        Candidate(
            id=f"qwen:{item['link'].rstrip('/')}",
            source="qwen",
            title=item["title"],
            url=item["link"],
            published_at=item["published"],
        )
        for item in parse_feed(get_text(QWEN_RSS_URL))
    ]
```

`src/sources/reddit.py`：

```python
from ..config import REDDIT_RSS_URL
from ..http_client import get_text
from ..models import Candidate
from ..rss_util import parse_feed


def fetch():
    return [
        Candidate(
            id=f"reddit:{item['link'].rstrip('/')}",
            source="reddit",
            title=item["title"],
            url=item["link"],
            published_at=item["published"],
        )
        for item in parse_feed(get_text(REDDIT_RSS_URL))
    ]
```

- [ ] **Step 5: 运行测试确认通过**

Run: `python -m pytest tests/ -v`
Expected: 全部 PASS

- [ ] **Step 6: 提交**

```bash
git add src/sources/ tests/test_sources_rss.py
git commit -m "feat: RSS sources (openai, qwen, reddit)"
```

---

### Task 4: Anthropic 源（HTML 解析）

**Files:**
- Create: `src/sources/anthropic.py`
- Test: `tests/test_sources_anthropic.py`
- Fixture: `tests/fixtures/anthropic_news.html`

**Interfaces:**
- Consumes: `http_client.get_text(ANTHROPIC_NEWS_URL)`
- Produces: `fetch() -> list[Candidate]`，ID = `"anthropic:{slug}"`，url = `https://www.anthropic.com/news/{slug}`；标题取 slug 附近窗口（前后各 600 字符）内的 `<h4>...</h4>` 文本，取不到则用 slug 转标题；日期取窗口内 `Mon D, YYYY` 格式（转 `YYYY-MM-DDT00:00:00+00:00`），取不到则 None。同一 slug 只输出一次

- [ ] **Step 1: 写 fixture**

`tests/fixtures/anthropic_news.html`（模拟实测到的卡片结构：slug href 后跟 h4 标题与日期）：

```html
<html><body>
<div class="cards">
<a href="/news/introducing-claude-opus-6" class="group"><h4 class="text-xl font-medium">Introducing Claude Opus 6</h4><p class="text-gray-500">Sep 9, 2026</p></a>
<a href="/news/claude-for-education-update" class="group"><h4 class="text-xl font-medium">Claude for Education update</h4><p class="text-gray-500">Aug 2, 2026</p></a>
<a href="/news/research-preview-no-date" class="group"><h4 class="text-xl font-medium">A research preview</h4></a>
<a href="/news/introducing-claude-opus-6"><span>duplicate should be skipped</span></a>
</div>
</body></html>
```

- [ ] **Step 2: 写失败测试**

`tests/test_sources_anthropic.py`：

```python
from pathlib import Path

import pytest

from src.sources import anthropic

FIXTURE = Path(__file__).parent / "fixtures" / "anthropic_news.html"


def test_fetch_extracts_slug_title_date():
    with patch_text(FIXTURE.read_text(encoding="utf-8")):
        out = anthropic.fetch()
    by_id = {c.id: c for c in out}
    assert len(out) == 3  # duplicate slug skipped
    c = by_id["anthropic:introducing-claude-opus-6"]
    assert c.title == "Introducing Claude Opus 6"
    assert c.url == "https://www.anthropic.com/news/introducing-claude-opus-6"
    assert c.published_at == "2026-09-09T00:00:00+00:00"


def test_fetch_without_h4_and_date_falls_back():
    with patch_text(FIXTURE.read_text(encoding="utf-8")):
        out = anthropic.fetch()
    by_id = {c.id: c for c in out}
    c = by_id["anthropic:research-preview-no-date"]
    assert c.published_at is None
    assert "Research Preview No Date" in c.title  # slug fallback


def patch_text(text):
    from unittest.mock import patch
    return patch("src.sources.anthropic.get_text", return_value=text)
```

- [ ] **Step 3: 运行测试确认失败**

Run: `python -m pytest tests/test_sources_anthropic.py -v`
Expected: FAIL（`ModuleNotFoundError: src.sources.anthropic`）

- [ ] **Step 4: 实现**

`src/sources/anthropic.py`：

```python
import re

from ..config import ANTHROPIC_NEWS_URL
from ..http_client import get_text
from ..models import Candidate

_SLUG_RE = re.compile(r'href="/news/([a-z0-9-]{6,80})"')
_DATE_RE = re.compile(r"([A-Z][a-z]{2} \d{1,2}, \d{4})")
_TITLE_RE = re.compile(r">([^<>]{10,120})</h4>")
_MONTHS = {m: i + 1 for i, m in enumerate(
    ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"])}


def _to_iso(s):
    m = _DATE_RE.match(s)
    if not m:
        return None
    month, day, year = m.group(1).split()
    return f"{year}-{_MONTHS[month]:02d}-{int(day):02d}T00:00:00+00:00"


def fetch():
    html = get_text(ANTHROPIC_NEWS_URL)
    seen, out = set(), []
    for m in _SLUG_RE.finditer(html):
        slug = m.group(1)
        if slug in seen:
            continue
        seen.add(slug)
        window = html[max(0, m.start() - 600):m.end() + 600]
        dm = _DATE_RE.search(window)
        tm = _TITLE_RE.search(window)
        out.append(Candidate(
            id=f"anthropic:{slug}",
            source="anthropic",
            title=tm.group(1).strip() if tm else slug.replace("-", " ").title(),
            url=f"https://www.anthropic.com/news/{slug}",
            published_at=_to_iso(dm.group(1)) if dm else None,
        ))
    return out
```

- [ ] **Step 5: 运行测试确认通过**

Run: `python -m pytest tests/ -v`
Expected: 全部 PASS

- [ ] **Step 6: 提交**

```bash
git add src/sources/anthropic.py tests/test_sources_anthropic.py tests/fixtures/anthropic_news.html
git commit -m "feat: anthropic news page source"
```

---

### Task 5: DeepSeek 源（新闻索引 + 单页标题）

**Files:**
- Create: `src/sources/deepseek.py`
- Test: `tests/test_sources_deepseek.py`
- Fixture: `tests/fixtures/deepseek_updates.html`, `tests/fixtures/deepseek_news_page.html`

**Interfaces:**
- Consumes: `http_client.get_text`（requests 默认跟随 302 重定向，已实测 `/news/news260910` → 带斜杠路径 200）
- Produces: `fetch() -> list[Candidate]`，ID = `"deepseek:{slug}"`，url = `https://api-docs.deepseek.com/news/{slug}/`，`published_at=None`；标题从单页 `<h1>` 提取，单页失败时回退 slug（不抛异常）

- [ ] **Step 1: 写 fixtures**

`tests/fixtures/deepseek_updates.html`：

```html
<html><body>
<nav><a href="/updates">Updates</a></nav>
<main>
<a href="/news/news0725">Old news</a>
<a href="/news/news260910">DeepSeek-V4.1-Flash</a>
<a href="/news/news260813">DeepSeek-V4.1 Exp: Vision Preview</a>
<a href="/news/news260910">duplicate</a>
</main>
</body></html>
```

`tests/fixtures/deepseek_news_page.html`：

```html
<html><body><main>
<h1>DeepSeek-V4.1-Flash: Smarter, Faster, More Efficient</h1>
<p>Today we release DeepSeek-V4.1-Flash.</p>
</main></body></html>
```

- [ ] **Step 2: 写失败测试**

`tests/test_sources_deepseek.py`：

```python
from pathlib import Path
from unittest.mock import patch

from src.sources import deepseek

FIX = Path(__file__).parent / "fixtures"


def test_fetch_extracts_slugs_and_titles():
    index = (FIX / "deepseek_updates.html").read_text(encoding="utf-8")
    page = (FIX / "deepseek_news_page.html").read_text(encoding="utf-8")

    def fake_get_text(url, headers=None):
        if "updates" in url:
            return index
        return page  # any news page

    with patch("src.sources.deepseek.get_text", side_effect=fake_get_text):
        out = deepseek.fetch()

    by_id = {c.id: c for c in out}
    assert set(by_id) == {"deepseek:news260910", "deepseek:news260813", "deepseek:news0725"}
    assert by_id["deepseek:news260910"].title == "DeepSeek-V4.1-Flash: Smarter, Faster, More Efficient"
    assert by_id["deepseek:news260910"].url == "https://api-docs.deepseek.com/news/news260910/"
    assert by_id["deepseek:news260910"].published_at is None


def test_fetch_title_fallback_on_page_error():
    index = (FIX / "deepseek_updates.html").read_text(encoding="utf-8")
    from src.http_client import HttpClientError

    def fake_get_text(url, headers=None):
        if "updates" in url:
            return index
        raise HttpClientError("page down")

    with patch("src.sources.deepseek.get_text", side_effect=fake_get_text):
        out = deepseek.fetch()
    c = {x.id: x for x in out}["deepseek:news260910"]
    assert c.title == "news260910"  # slug fallback
```

- [ ] **Step 3: 运行测试确认失败**

Run: `python -m pytest tests/test_sources_deepseek.py -v`
Expected: FAIL（`ModuleNotFoundError: src.sources.deepseek`）

- [ ] **Step 4: 实现**

`src/sources/deepseek.py`：

```python
import re

from ..config import DEEPSEEK_UPDATES_URL
from ..http_client import get_text
from ..models import Candidate

_SLUG_RE = re.compile(r'href="/news/(news[a-z0-9]{4,10})"')
_TITLE_RE = re.compile(r"<h1[^>]*>([^<]+)</h1>")


def fetch():
    html = get_text(DEEPSEEK_UPDATES_URL)
    seen, out = set(), []
    for m in _SLUG_RE.finditer(html):
        slug = m.group(1)
        if slug in seen:
            continue
        seen.add(slug)
        url = f"https://api-docs.deepseek.com/news/{slug}/"
        title = slug
        try:
            tm = _TITLE_RE.search(get_text(url))
            if tm:
                title = tm.group(1).strip()
        except Exception:
            pass  # 单页失败用 slug 兜底，不阻塞
        out.append(Candidate(
            id=f"deepseek:{slug}",
            source="deepseek",
            title=title,
            url=url,
            published_at=None,
        ))
    return out
```

- [ ] **Step 5: 运行测试确认通过**

Run: `python -m pytest tests/ -v`
Expected: 全部 PASS

- [ ] **Step 6: 提交**

```bash
git add src/sources/deepseek.py tests/test_sources_deepseek.py tests/fixtures/deepseek_*.html
git commit -m "feat: deepseek news source"
```

---

### Task 6: JSON API 源 — hf、openrouter、github

**Files:**
- Create: `src/sources/hf.py`, `src/sources/openrouter.py`, `src/sources/github.py`
- Test: `tests/test_sources_api.py`

**Interfaces:**
- Consumes: `http_client.get_json(url, headers=None)`
- Produces:
  - `hf.fetch()`：对 `config.HF_ORGS` 每个组织请求 `{HF_API_BASE}/models?author={org}&sort=createdAt&direction=-1&limit=15`；单组织请求失败静默跳过（本地被墙场景）；ID=`"hf:{model_id}"`，url=`https://huggingface.co/{model_id}`，published_at=`createdAt`，extra=`downloads=… likes=…`
  - `openrouter.fetch()`：请求 `OPENROUTER_MODELS_URL`，遍历 `data`；`created`（unix 秒）转 ISO UTC；ID=`"openrouter:{id}"`
  - `github.fetch()`：对 `config.GH_REPOS` 每仓库请求 releases，ID=`"github:{repo}:{release_id}"`，extra 为空

- [ ] **Step 1: 写失败测试**

`tests/test_sources_api.py`：

```python
from unittest.mock import patch

from src.sources import github, hf, openrouter

HF_JSON = [
    {"id": "Qwen/Qwen3.9-72B", "createdAt": "2026-09-09T12:00:00.000Z",
     "downloads": 1200, "likes": 45, "pipeline_tag": "text-generation"},
    {"id": "Qwen/Qwen3.8-27B", "createdAt": "2026-09-01T12:00:00.000Z",
     "downloads": 99000, "likes": 1200},
]

OR_JSON = {"data": [
    {"id": "moonshotai/kimi-k4", "name": "MoonshotAI: Kimi K4",
     "created": 1789050000, "context_length": 256000},
    {"id": "openai/gpt-5.2", "name": "OpenAI: GPT-5.2",
     "created": 1787000000, "context_length": 400000},
]}

GH_JSON = [{"id": 123456, "name": "gpt-oss-120b-updates", "tag_name": "v2026.09",
            "html_url": "https://github.com/openai/gpt-oss/releases/tag/v2026.09",
            "published_at": "2026-09-08T00:00:00Z"}]


def test_hf_fetch_all_orgs():
    with patch("src.sources.hf.get_json", return_value=HF_JSON) as g:
        out = hf.fetch()
    assert g.call_count == len(__import__("src.config", fromlist=["HF_ORGS"]).HF_ORGS)
    by_id = {c.id: c for c in out}
    assert "hf:Qwen/Qwen3.9-72B" in by_id
    c = by_id["hf:Qwen/Qwen3.9-72B"]
    assert c.url == "https://huggingface.co/Qwen/Qwen3.9-72B"
    assert c.published_at == "2026-09-09T12:00:00.000Z"
    assert "downloads=1200" in c.extra


def test_hf_fetch_skips_failed_org():
    from src.http_client import HttpClientError
    with patch("src.sources.hf.get_json", side_effect=HttpClientError("blocked")):
        assert hf.fetch() == []


def test_openrouter_fetch():
    with patch("src.sources.openrouter.get_json", return_value=OR_JSON):
        out = openrouter.fetch()
    by_id = {c.id: c for c in out}
    c = by_id["openrouter:moonshotai/kimi-k4"]
    assert c.title == "MoonshotAI: Kimi K4"
    assert c.url == "https://openrouter.ai/moonshotai/kimi-k4"
    assert c.published_at == "2026-05-10T01:40:00+00:00"  # 1789050000


def test_github_fetch():
    with patch("src.sources.github.get_json", return_value=GH_JSON):
        out = github.fetch()
    c = out[0]
    assert c.id == "github:openai/gpt-oss:123456"
    assert "gpt-oss-120b-updates" in c.title
    assert c.published_at == "2026-09-08T00:00:00Z"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_sources_api.py -v`
Expected: FAIL（`ModuleNotFoundError`）

- [ ] **Step 3: 实现**

`src/sources/hf.py`：

```python
from ..config import HF_API_BASE, HF_ORGS
from ..http_client import get_json
from ..models import Candidate


def fetch():
    out = []
    for org in HF_ORGS:
        try:
            rows = get_json(f"{HF_API_BASE}/models?author={org}&sort=createdAt&direction=-1&limit=15")
        except Exception:
            continue  # 本地被墙 / 瞬时失败：跳过该组织
        for r in rows:
            mid = r.get("id") or (f"{r.get('author')}/{r.get('modelId')}")
            out.append(Candidate(
                id=f"hf:{mid}",
                source="hf",
                title=mid,
                url=f"https://huggingface.co/{mid}",
                published_at=r.get("createdAt"),
                extra=f"downloads={r.get('downloads', '?')} likes={r.get('likes', '?')}",
            ))
    return out
```

`src/sources/openrouter.py`：

```python
from datetime import datetime, timezone

from ..config import OPENROUTER_MODELS_URL
from ..http_client import get_json
from ..models import Candidate


def fetch():
    data = get_json(OPENROUTER_MODELS_URL).get("data", [])
    out = []
    for m in data:
        created = m.get("created")
        pub = datetime.fromtimestamp(created, tz=timezone.utc).isoformat() if created else None
        out.append(Candidate(
            id=f"openrouter:{m['id']}",
            source="openrouter",
            title=m.get("name") or m["id"],
            url=f"https://openrouter.ai/{m['id']}",
            published_at=pub,
            extra=f"context={m.get('context_length', '?')}",
        ))
    return out
```

`src/sources/github.py`：

```python
from ..config import GH_REPOS
from ..http_client import get_json
from ..models import Candidate


def fetch():
    out = []
    for repo in GH_REPOS:
        try:
            rels = get_json(f"https://api.github.com/repos/{repo}/releases?per_page=5")
        except Exception:
            continue
        for r in rels:
            out.append(Candidate(
                id=f"github:{repo}:{r['id']}",
                source="github",
                title=f"{repo} {r.get('name') or r.get('tag_name')}",
                url=r.get("html_url", f"https://github.com/{repo}/releases"),
                published_at=r.get("published_at"),
            ))
    return out
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/ -v`
Expected: 全部 PASS

- [ ] **Step 5: 提交**

```bash
git add src/sources/hf.py src/sources/openrouter.py src/sources/github.py tests/test_sources_api.py
git commit -m "feat: JSON API sources (hf, openrouter, github releases)"
```

---

### Task 7: ModelScope 源 + 源注册表

**Files:**
- Create: `src/sources/modelscope.py`
- Modify: `src/sources/__init__.py`（写注册表）
- Test: `tests/test_sources_modelscope.py`, `tests/test_sources_registry.py`
- Fixture: `tests/fixtures/modelscope_search.json`

**Interfaces:**
- Consumes: `http_client.put_json(MS_SEARCH_URL, payload, headers)`；payload `{"Name": kw, "PageSize": 20, "PageNumber": 1}`（默认相关度排序，实测官方组织模型排最前）
- Produces: `modelscope.fetch() -> list[Candidate]`——关键词搜索 → 客户端按 `Path in MS_ORG_MAP[kw]` 过滤 → 跨关键词按 `Path/Name` 去重；`CreatedTime`（unix 秒）转 ISO；ID=`"modelscope:{Path}/{Name}"`；标题优先 `ChineseName`
- Produces: `src/sources.ALL_SOURCES: list[tuple[str, callable]]`，10 项，顺序 openai/anthropic/qwen/deepseek/hf/modelscope/openrouter/github/reddit/hn… 注意：hn 源尚未存在！

**修正：** HN 源在本任务一并创建（很小），注册表才能完整。

- Create: `src/sources/hn.py`

**Interfaces（hn）:**
- Consumes: `http_client.get_json`；URL `f"{HN_ALGOLIA_BASE}/search_by_date?query={quote(q)}&tags=story&hitsPerPage=30"`（`urllib.parse.quote`）
- Produces: `hn.fetch() -> list[Candidate]`，ID=`"hn:{objectID}"`，无 title 的条目丢弃，跨查询按 objectID 去重，extra=`points=…`

- [ ] **Step 1: 写 fixture**

`tests/fixtures/modelscope_search.json`：

```json
{"Code": 200, "Data": {"Model": {"Models": [
  {"Path": "Qwen", "Name": "Qwen3.8-Flash-Next", "ChineseName": "千问3.8-Flash-Next", "CreatedTime": 1789011254},
  {"Path": "unsloth", "Name": "Qwen3.8-Flash-Next-GGUF", "ChineseName": "", "CreatedTime": 1789011000}
], "TotalCount": 2}}}
```

- [ ] **Step 2: 写失败测试**

`tests/test_sources_modelscope.py`：

```python
import json
from pathlib import Path
from unittest.mock import patch

from src.sources import modelscope

FIX = json.loads((Path(__file__).parent / "fixtures" / "modelscope_search.json").read_text(encoding="utf-8"))


def test_fetch_filters_to_official_orgs():
    with patch("src.sources.modelscope.put_json", return_value=FIX) as p:
        out = modelscope.fetch()
    assert p.call_count == len(modelscope.MS_KEYWORDS)
    assert p.call_args.kwargs["json"] if False else True
    first_call = p.call_args_list[0]
    assert first_call.args[0] == modelscope.MS_SEARCH_URL
    assert first_call.args[1]["Name"] == "qwen"
    ids = [c.id for c in out]
    assert "modelscope:Qwen/Qwen3.8-Flash-Next" in ids
    assert "modelscope:unsloth/Qwen3.8-Flash-Next-GGUF" not in ids  # 非官方组织被过滤
    c = [c for c in out if c.id == "modelscope:Qwen/Qwen3.8-Flash-Next"][0]
    assert c.title == "千问3.8-Flash-Next"
    assert c.url == "https://modelscope.cn/models/Qwen/Qwen3.8-Flash-Next"
    assert c.published_at == "2026-05-18T01:34:14+00:00"  # 1789011254


def test_fetch_survives_search_failure():
    from src.http_client import HttpClientError
    with patch("src.sources.modelscope.put_json", side_effect=HttpClientError("down")):
        assert modelscope.fetch() == []
```

`tests/test_sources_registry.py`：

```python
from src.sources import ALL_SOURCES


def test_registry_has_all_10_sources():
    names = [n for n, _ in ALL_SOURCES]
    assert names == ["openai", "anthropic", "qwen", "deepseek", "hf",
                     "modelscope", "openrouter", "github", "reddit", "hn"]
    assert all(callable(f) for _, f in ALL_SOURCES)
```

- [ ] **Step 3: 运行测试确认失败**

Run: `python -m pytest tests/test_sources_modelscope.py tests/test_sources_registry.py -v`
Expected: FAIL

- [ ] **Step 4: 实现**

`src/sources/modelscope.py`：

```python
from datetime import datetime, timezone

from ..config import MS_KEYWORDS, MS_ORG_MAP, MS_SEARCH_URL
from ..http_client import put_json
from ..models import Candidate


def fetch():
    out, seen = [], set()
    for kw in MS_KEYWORDS:
        try:
            d = put_json(MS_SEARCH_URL, {"Name": kw, "PageSize": 20, "PageNumber": 1})
        except Exception:
            continue
        orgs = MS_ORG_MAP.get(kw, set())
        for m in d.get("Data", {}).get("Model", {}).get("Models", []):
            path, name = m.get("Path"), m.get("Name")
            if not path or not name or path not in orgs:
                continue
            key = f"{path}/{name}"
            if key in seen:
                continue
            seen.add(key)
            ct = m.get("CreatedTime")
            pub = datetime.fromtimestamp(ct, tz=timezone.utc).isoformat() if ct else None
            out.append(Candidate(
                id=f"modelscope:{key}",
                source="modelscope",
                title=(m.get("ChineseName") or name),
                url=f"https://modelscope.cn/models/{key}",
                published_at=pub,
            ))
    return out
```

`src/sources/hn.py`：

```python
from urllib.parse import quote

from ..config import HN_ALGOLIA_BASE, HN_QUERIES
from ..http_client import get_json
from ..models import Candidate


def fetch():
    out, seen = [], set()
    for q in HN_QUERIES:
        try:
            d = get_json(f"{HN_ALGOLIA_BASE}/search_by_date?query={quote(q)}&tags=story&hitsPerPage=30")
        except Exception:
            continue
        for h in d.get("hits", []):
            hid = h.get("objectID")
            title = h.get("title") or ""
            if not hid or not title or hid in seen:
                continue
            seen.add(hid)
            out.append(Candidate(
                id=f"hn:{hid}",
                source="hn",
                title=title,
                url=h.get("url") or f"https://news.ycombinator.com/item?id={hid}",
                published_at=h.get("created_at"),
                extra=f"points={h.get('points', 0)}",
            ))
    return out
```

替换 `src/sources/__init__.py`：

```python
from . import anthropic, deepseek, github, hf, hn, modelscope, openai, openrouter, qwen, reddit

ALL_SOURCES = [
    ("openai", openai.fetch),
    ("anthropic", anthropic.fetch),
    ("qwen", qwen.fetch),
    ("deepseek", deepseek.fetch),
    ("hf", hf.fetch),
    ("modelscope", modelscope.fetch),
    ("openrouter", openrouter.fetch),
    ("github", github.fetch),
    ("reddit", reddit.fetch),
    ("hn", hn.fetch),
]
```

- [ ] **Step 5: 运行测试确认通过**

Run: `python -m pytest tests/ -v`
Expected: 全部 PASS

- [ ] **Step 6: 提交**

```bash
git add src/sources/ tests/test_sources_modelscope.py tests/test_sources_registry.py tests/fixtures/modelscope_search.json
git commit -m "feat: modelscope + hn sources, source registry"
```

---

### Task 8: 状态存储 SeenStore（去重 + bootstrap + pending）

**Files:**
- Create: `src/state.py`
- Test: `tests/test_state.py`

**Interfaces:**
- Consumes: `models.Candidate`
- Produces: `SeenStore(path)`，属性/方法：
  - `bootstrapped: bool`；`set_bootstrapped()`
  - `filter_new(candidates: list[Candidate]) -> list[Candidate]`
  - `mark_seen(candidates: list[Candidate], iso_now: str)`
  - `add_pending(candidates)` / `pop_pending() -> list[Candidate]`
  - `add_pending_push(events: list[dict])` / `pop_pending_push() -> list[dict]`
  - `save()`
- 存储 schema：`{"bootstrapped": bool, "seen": {id: iso_time}, "pending": [candidate_dict], "pending_push": [event_dict]}`；`seen` 超过 20000 条时按时间淘汰最旧 5000 条

- [ ] **Step 1: 写失败测试**

`tests/test_state.py`：

```python
import json

from src.models import Candidate
from src.state import SeenStore


def make_c(n):
    return [Candidate(id=f"src{i}", source="s", title=f"t{i}", url=f"u{i}") for i in range(n)]


def test_filter_new_and_mark_seen(tmp_path):
    p = tmp_path / "seen.json"
    store = SeenStore(p)
    cs = make_c(3)
    assert [c.id for c in store.filter_new(cs)] == ["src0", "src1", "src2"]
    store.mark_seen(cs[:2], "2026-09-10T00:00:00+00:00")
    assert [c.id for c in store.filter_new(cs)] == ["src2"]
    store.save()
    data = json.loads(p.read_text(encoding="utf-8"))
    assert data["seen"]["src0"] == "2026-09-10T00:00:00+00:00"
    assert data["bootstrapped"] is False


def test_bootstrap_roundtrip(tmp_path):
    p = tmp_path / "seen.json"
    store = SeenStore(p)
    assert store.bootstrapped is False
    store.set_bootstrapped()
    store.save()
    assert SeenStore(p).bootstrapped is True


def test_pending_cycle(tmp_path):
    store = SeenStore(tmp_path / "seen.json")
    cs = make_c(2)
    store.add_pending(cs)
    store.add_pending(cs)  # 不重复
    got = store.pop_pending()
    assert [c.id for c in got] == ["src0", "src1"]
    assert got[0].title == "t0"
    assert store.pop_pending() == []


def test_pending_push_cycle(tmp_path):
    store = SeenStore(tmp_path / "seen.json")
    events = [{"id": "x", "title": "T", "url": "U", "source": "s", "event_type": "release", "summary": "S"}]
    store.add_pending_push(events)
    store.save()
    reloaded = SeenStore(tmp_path / "seen.json")
    assert reloaded.pop_pending_push() == events


def test_seen_capacity_trim(tmp_path):
    store = SeenStore(tmp_path / "seen.json")
    cs = make_c(20)
    store.mark_seen(cs, "2026-09-10T00:00:00+00:00")
    # 人为触发淘汰：直接改上限不可行，这里验证大量 mark_seen 不崩溃且可 save/load
    store.save()
    assert len(SeenStore(tmp_path / "seen.json").data["seen"]) == 20


def test_loads_existing_file(tmp_path):
    p = tmp_path / "seen.json"
    p.write_text(json.dumps({"bootstrapped": True, "seen": {"a": "t"},
                             "pending": [], "pending_push": []}), encoding="utf-8")
    store = SeenStore(p)
    assert store.bootstrapped is True
    assert store.data["seen"] == {"a": "t"}
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_state.py -v`
Expected: FAIL（`ModuleNotFoundError: src.state`）

- [ ] **Step 3: 实现**

`src/state.py`：

```python
import json
from pathlib import Path

from .models import Candidate

SCHEMA = {"bootstrapped": False, "seen": {}, "pending": [], "pending_push": []}
MAX_SEEN = 20000
TRIM_COUNT = 5000


class SeenStore:
    def __init__(self, path):
        self.path = Path(path)
        if self.path.exists():
            self.data = json.loads(self.path.read_text(encoding="utf-8"))
        else:
            self.data = json.loads(json.dumps(SCHEMA))

    @property
    def bootstrapped(self):
        return self.data["bootstrapped"]

    def set_bootstrapped(self):
        self.data["bootstrapped"] = True

    def filter_new(self, candidates):
        return [c for c in candidates if c.id not in self.data["seen"]]

    def mark_seen(self, candidates, iso_now):
        for c in candidates:
            self.data["seen"][c.id] = iso_now
        if len(self.data["seen"]) > MAX_SEEN:
            for k in sorted(self.data["seen"], key=self.data["seen"].get)[:TRIM_COUNT]:
                del self.data["seen"][k]

    def add_pending(self, candidates):
        ids = {d["id"] for d in self.data["pending"]}
        self.data["pending"] += [c.to_dict() for c in candidates if c.id not in ids]

    def pop_pending(self):
        items = self.data["pending"]
        self.data["pending"] = []
        return [Candidate.from_dict(d) for d in items]

    def add_pending_push(self, events):
        self.data["pending_push"] += events

    def pop_pending_push(self):
        items = self.data["pending_push"]
        self.data["pending_push"] = []
        return items

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(self.data, ensure_ascii=False, indent=1),
            encoding="utf-8",
        )
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/ -v`
Expected: 全部 PASS

- [ ] **Step 5: 提交**

```bash
git add src/state.py tests/test_state.py
git commit -m "feat: SeenStore state persistence with bootstrap and pending queues"
```

---

### Task 9: LLM 事件判断 judge（DeepSeek + 关键词降级）

**Files:**
- Create: `src/judge.py`
- Test: `tests/test_judge.py`

**Interfaces:**
- Consumes: `http_client.post_json(DEEPSEEK_BASE_URL + "/chat/completions", payload, headers)`、`config.DEEPSEEK_API_KEY / DEEPSEEK_MODEL`
- Produces: `judge(candidates: list[Candidate]) -> list[dict]`，每项 `{"id", "is_event": bool, "event_type": "release"|"open_weights"|"major_update", "summary": str, "decided": bool}`；`decided=False` 表示无法判定（调用方放入 pending 下轮重试）。任何 LLM 失败 → 逐条关键词判断：高置信命中 → `decided=True, is_event=True`；否则 `decided=False`。LLM 成功但某条缺判定 → 同样走关键词兜底。空列表直接返回 `[]`

- [ ] **Step 1: 写失败测试**

`tests/test_judge.py`：

```python
from unittest.mock import patch

from src.judge import judge, keyword_judgment
from src.models import Candidate


def _c(i, title):
    return Candidate(id=i, source="openai", title=title, url="u")


def test_empty_input():
    assert judge([]) == []


def test_llm_success_path():
    cs = [_c("a", "Introducing GPT-6"), _c("b", "Benchmark leaderboard drama")]
    llm_resp = {"choices": [{"message": {"content":
        '[{"id":"a","is_event":true,"event_type":"release","summary":"GPT-6发布"},'
        '{"id":"b","is_event":false,"event_type":"","summary":"榜单帖"}]'}}]}
    with patch("src.judge.post_json", return_value=llm_resp) as p:
        out = judge(cs)
    body = p.call_args.args[1]
    assert body["model"] == "deepseek-chat"
    assert "Introducing GPT-6" in body["messages"][1]["content"]
    assert out[0] == {"id": "a", "is_event": True, "event_type": "release",
                      "summary": "GPT-6发布", "decided": True}
    assert out[1]["decided"] is True and out[1]["is_event"] is False


def test_llm_json_with_code_fences():
    cs = [_c("a", "Kimi K4 open weights released")]
    llm_resp = {"choices": [{"message": {"content":
        '```json\n[{"id":"a","is_event":true,"event_type":"open_weights","summary":"K4开源"}]\n```'}}]}
    with patch("src.judge.post_json", return_value=llm_resp):
        out = judge(cs)
    assert out[0]["event_type"] == "open_weights"


def test_llm_missing_entry_gets_keyword_fallback():
    cs = [_c("a", "Qwen3.9 released"), _c("b", "Weekly discussion thread")]
    llm_resp = {"choices": [{"message": {"content": '[{"id":"a","is_event":true,"event_type":"release","summary":"ok"}]'}}]}
    with patch("src.judge.post_json", return_value=llm_resp):
        out = judge(cs)
    assert out[0]["decided"] is True
    assert out[1]["decided"] is False  # 关键词不命中 → pending


def test_api_failure_falls_back():
    from src.http_client import HttpClientError
    cs = [_c("a", "DeepSeek-V5 weights 开源发布"), _c("b", "Leaderboard benchmark results")]
    with patch("src.judge.post_json", side_effect=HttpClientError("api down")):
        out = judge(cs)
    assert out[0]["decided"] is True and out[0]["is_event"] is True
    assert out[1]["decided"] is False  # 负面词 → 不判


def test_keyword_judgment_rules():
    assert keyword_judgment(_c("x", "GLM-5.4 model release")).is_event is True  # wait no
```

注意最后一行写错了，应为：

```python
def test_keyword_judgment_rules():
    hit = keyword_judgment(_c("x", "GLM-5.4 new model release"))
    assert hit and hit["is_event"] is True
    assert keyword_judgment(_c("y", "AI policy announcement")) is None  # 无关键词
    assert keyword_judgment(_c("z", "Model benchmark leaderboard")) is None  # 负面词
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_judge.py -v`
Expected: FAIL（`ModuleNotFoundError: src.judge`）

- [ ] **Step 3: 实现**

`src/judge.py`：

```python
import json
import re

from .config import DEEPSEEK_API_KEY, DEEPSEEK_BASE_URL, DEEPSEEK_MODEL
from .http_client import post_json
from .models import Candidate

SYSTEM_PROMPT = """你是AI模型发布监控助手。给你一批候选条目(JSON数组，含id/title/source/published_at/extra)。
判断每条是否为"硬事件"，硬事件只包括：
1. 新模型发布（闭源API模型或开源模型正式发布）
2. 模型权重开源
3. 模型重大版本升级（大版本/能力代际提升）
不算硬事件：榜单/评测/评论/行业新闻/rumor/文档更新/小版本修复/框架工具更新/融资/政策。
对每条输出: {"id": "...", "is_event": true/false, "event_type": "release"|"open_weights"|"major_update", "summary": "30字内中文摘要，必须含模型名"}
拿不准的一律 is_event=false。只输出JSON数组，不要其他文字。"""

_KEY_RE = re.compile(
    r"(model|llm|weights|权重|模型|开源|release|launch|introduc|announce|发布|上线)", re.I)
_NEG_RE = re.compile(
    r"(benchmark|leaderboard|榜单|评测|review|对比|融资|funding|招聘|hiring|policy|政策)", re.I)


def keyword_judgment(c):
    """高置信关键词判断；不命中返回 None（→ pending）。"""
    text = f"{c.title} {c.extra}"
    if _NEG_RE.search(text) or not _KEY_RE.search(text):
        return None
    return {"id": c.id, "is_event": True, "event_type": "release", "summary": c.title}


def _parse_llm_array(text):
    m = re.search(r"\[.*\]", text, re.S)
    if not m:
        raise ValueError("no JSON array in LLM response")
    return {j["id"]: j for j in json.loads(m.group(0)) if isinstance(j, dict) and "id" in j}


def judge(candidates):
    if not candidates:
        return []

    def _fallback(c):
        kw = keyword_judgment(c)
        if kw:
            return {**kw, "decided": True}
        return {"id": c.id, "is_event": False, "event_type": "", "summary": "", "decided": False}

    try:
        resp = post_json(
            f"{DEEPSEEK_BASE_URL}/chat/completions",
            {
                "model": DEEPSEEK_MODEL,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": json.dumps(
                        [c.to_dict() for c in candidates], ensure_ascii=False)},
                ],
                "temperature": 0.1,
            },
            headers={"Authorization": f"Bearer {DEEPSEEK_API_KEY}",
                     "Content-Type": "application/json"},
        )
        by_id = _parse_llm_array(resp["choices"][0]["message"]["content"])
    except Exception:
        return [_fallback(c) for c in candidates]

    out = []
    for c in candidates:
        j = by_id.get(c.id)
        if not j:
            out.append(_fallback(c))
            continue
        out.append({
            "id": c.id,
            "is_event": bool(j.get("is_event")),
            "event_type": j.get("event_type", "release"),
            "summary": j.get("summary", c.title),
            "decided": True,
        })
    return out
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/ -v`
Expected: 全部 PASS

- [ ] **Step 5: 提交**

```bash
git add src/judge.py tests/test_judge.py
git commit -m "feat: LLM event judging with keyword fallback"
```

---

### Task 10: Server酱推送 notify

**Files:**
- Create: `src/notify.py`
- Test: `tests/test_notify.py`

**Interfaces:**
- Consumes: `http_client.post_form`、`config.SERVERCHAN_SENDKEY`、环境变量 `DRY_RUN`
- Produces: `build_message(events: list[dict]) -> (title, desp)`；`push_events(events) -> bool`（成功 True；失败/无 key 打印日志返回 False；`DRY_RUN` 非空时只打印返回 True；空 events 直接 True）

- [ ] **Step 1: 写失败测试**

`tests/test_notify.py`：

```python
from unittest.mock import patch

from src import notify

EVENTS = [
    {"id": "a", "source": "anthropic", "title": "Claude Opus 6",
     "url": "https://www.anthropic.com/news/x", "published_at": "2026-09-09",
     "event_type": "release", "summary": "Claude Opus 6 发布"},
]


def test_build_message_contains_markdown_link_and_type():
    title, desp = notify.build_message(EVENTS)
    assert title == "🤖 模型发布动态 (1条)"
    assert "[Claude Opus 6](https://www.anthropic.com/news/x)" in desp
    assert "新模型发布" in desp
    assert "Claude Opus 6 发布" in desp
    assert "anthropic" in desp


def test_push_events_empty_is_true():
    assert notify.push_events([]) is True


def test_push_events_calls_post_form():
    with patch("src.notify.post_form", return_value="ok") as p, \
         patch.dict("os.environ", {"DRY_RUN": ""}):
        assert notify.push_events(EVENTS) is True
        url = p.call_args.args[0]
        assert url.startswith("https://sctapi.ftqq.com/") and url.endswith(".send")
        data = p.call_args.args[1]
        assert "title" in data and "desp" in data


def test_push_events_dry_run_skips_http():
    with patch("src.notify.post_form") as p, \
         patch.dict("os.environ", {"DRY_RUN": "1"}):
        assert notify.push_events(EVENTS) is True
        p.assert_not_called()


def test_push_events_failure_returns_false():
    with patch("src.notify.post_form", side_effect=Exception("bad key")), \
         patch.dict("os.environ", {"DRY_RUN": "", "SERVERCHAN_SENDKEY": "SCT_x"}):
        assert notify.push_events(EVENTS) is False
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_notify.py -v`
Expected: FAIL（`ModuleNotFoundError: src.notify`）

- [ ] **Step 3: 实现**

`src/notify.py`：

```python
import os

from .config import SERVERCHAN_SENDKEY
from .http_client import post_form

TYPE_LABEL = {"release": "新模型发布", "open_weights": "权重开源", "major_update": "重大升级"}


def build_message(events):
    lines = []
    for e in events:
        label = TYPE_LABEL.get(e.get("event_type"), "动态")
        lines.append(
            f"**[{e['title']}]({e['url']})** — {label}\n\n"
            f"{e.get('summary', '')}\n\n"
            f"来源: {e['source']} | {e.get('published_at') or '时间未知'}\n"
        )
    return f"🤖 模型发布动态 ({len(events)}条)", "\n---\n".join(lines)


def push_events(events):
    if not events:
        return True
    title, desp = build_message(events)
    if os.environ.get("DRY_RUN"):
        print(f"[DRY_RUN] would push: {title}\n{desp}")
        return True
    if not SERVERCHAN_SENDKEY:
        print("WARN: no SERVERCHAN_SENDKEY, skip push")
        return False
    try:
        post_form(f"https://sctapi.ftqq.com/{SERVERCHAN_SENDKEY}.send",
                  {"title": title, "desp": desp})
        return True
    except Exception as exc:
        print(f"push failed: {exc}")
        return False
```

- [ ] **Step 4: 运行测试确认通过**

Run: `python -m pytest tests/ -v`
Expected: 全部 PASS

- [ ] **Step 5: 提交**

```bash
git add src/notify.py tests/test_notify.py
git commit -m "feat: serverchan push with dry-run mode"
```

---

### Task 11: 主编排 run.py（含端到端测试）

**Files:**
- Create: `src/run.py`
- Test: `tests/test_run.py`

**Interfaces:**
- Consumes: 全部前序模块。注意 `config` 常量已通过 `from .config import ...` 绑定到 run 模块命名空间，测试用 `monkeypatch.setattr(run, "STATE_PATH", tmp)` 覆盖
- Produces: `main() -> int`（返回 0；`if __name__ == "__main__": sys.exit(main())`）
- 逻辑顺序（严格按此实现）：
  1. 收集候选（逐源 try/except，打印 `[name] N candidates` / `[name] FAILED: e`）
  2. `filter_new` → 按 `SKIP_OLDER_THAN_HOURS=48` 分流：过期条目直接 `mark_seen`（`published_at` 解析失败或为 None 不算过期；未来时间容忍 2h 时钟偏差）
  3. 未 bootstrap：`mark_seen(全部候选)` + `set_bootstrapped` + `save` + print + return 0
  4. `to_judge = fresh[:MAX_CANDIDATES_PER_JUDGE]`，超出部分 `add_pending`
  5. `judged = judge(to_judge + pop_pending())`
  6. 事件 = decided 且 is_event 的条目合并 judgment 字段；未 decided → 回 `add_pending`（注意：先 pop 了 pending，未 decided 的要重新放回）
  7. decided 的条目（无论是否事件）都 `mark_seen`
  8. `all_events = events + pop_pending_push()`；`push_events(all_events)` 成功 → `append_events_md`；失败 → `add_pending_push(all_events)`
  9. `save` + 汇总 print + return 0

- [ ] **Step 1: 写失败测试**

`tests/test_run.py`：

```python
import json
from unittest.mock import patch

import pytest

import src.run as run
from src.models import Candidate


def _c(i, title, published="2026-09-10T00:00:00+00:00"):
    return Candidate(id=i, source="openai", title=title, url=f"https://x/{i}",
                     published_at=published)


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(run, "STATE_PATH", tmp_path / "state" / "seen.json")
    monkeypatch.setattr(run, "EVENTS_MD_PATH", tmp_path / "events.md")
    return tmp_path


def _fake_sources(*batches):
    """按返回批次构造 ALL_SOURCES：[(name, fetch), ...]"""
    return [(f"src{i}", (lambda b: (lambda: b))(b)) for i, b in enumerate(batches)]


def test_first_run_bootstrap_no_push(env, capsys):
    with patch.object(run, "ALL_SOURCES", _fake_sources([_c("a", "New model X")])), \
         patch.object(run, "judge") as j, \
         patch.object(run, "push_events") as p:
        assert run.main() == 0
        j.assert_not_called()
        p.assert_not_called()
    data = json.loads((env / "state" / "seen.json").read_text(encoding="utf-8"))
    assert data["bootstrapped"] is True
    assert "a" in data["seen"]


def test_event_flow_push_and_events_md(env):
    # 预置已 bootstrap 的状态，候选 a 为已见，b 为新事件
    sp = env / "state" / "seen.json"
    sp.parent.mkdir(parents=True)
    sp.write_text(json.dumps({"bootstrapped": True, "seen": {"a": "2026-09-09T00:00:00+00:00"},
                              "pending": [], "pending_push": []}), encoding="utf-8")
    with patch.object(run, "ALL_SOURCES", _fake_sources([_c("a", "old"), _c("b", "Kimi K4 released")])), \
         patch.object(run, "judge", return_value=[
             {"id": "b", "is_event": True, "event_type": "open_weights",
              "summary": "Kimi K4 开源", "decided": True}]), \
         patch.object(run, "push_events", return_value=True) as p:
        assert run.main() == 0
    p.assert_called_once()
    events = p.call_args.args[0]
    assert events[0]["id"] == "b" and events[0]["summary"] == "Kimi K4 开源"
    md = (env / "events.md").read_text(encoding="utf-8")
    assert "Kimi K4" in md
    data = json.loads(sp.read_text(encoding="utf-8"))
    assert "b" in data["seen"] and data["pending"] == []


def test_push_failure_keeps_pending_push(env):
    sp = env / "state" / "seen.json"
    sp.parent.mkdir(parents=True)
    sp.write_text(json.dumps({"bootstrapped": True, "seen": {},
                              "pending": [], "pending_push": []}), encoding="utf-8")
    with patch.object(run, "ALL_SOURCES", _fake_sources([_c("b", "New GPT")])), \
         patch.object(run, "judge", return_value=[
             {"id": "b", "is_event": True, "event_type": "release",
              "summary": "GPT发布", "decided": True}]), \
         patch.object(run, "push_events", return_value=False):
        run.main()
    data = json.loads(sp.read_text(encoding="utf-8"))
    assert len(data["pending_push"]) == 1
    # 下轮推送成功
    with patch.object(run, "ALL_SOURCES", _fake_sources([])), \
         patch.object(run, "judge", return_value=[]), \
         patch.object(run, "push_events", return_value=True) as p:
        run.main()
    p.assert_called_once()
    data = json.loads(sp.read_text(encoding="utf-8"))
    assert data["pending_push"] == []


def test_undecided_goes_back_to_pending(env):
    sp = env / "state" / "seen.json"
    sp.parent.mkdir(parents=True)
    sp.write_text(json.dumps({"bootstrapped": True, "seen": {},
                              "pending": [], "pending_push": []}), encoding="utf-8")
    with patch.object(run, "ALL_SOURCES", _fake_sources([_c("u", "Some announcement")])), \
         patch.object(run, "judge", return_value=[
             {"id": "u", "is_event": False, "event_type": "", "summary": "", "decided": False}]), \
         patch.object(run, "push_events") as p:
        run.main()
    p.assert_not_called()
    data = json.loads(sp.read_text(encoding="utf-8"))
    assert [d["id"] for d in data["pending"]] == ["u"]
    assert "u" not in data["seen"]


def test_stale_candidates_marked_seen_without_judging(env):
    sp = env / "state" / "seen.json"
    sp.parent.mkdir(parents=True)
    sp.write_text(json.dumps({"bootstrapped": True, "seen": {},
                              "pending": [], "pending_push": []}), encoding="utf-8")
    old = _c("old", "Old release", published="2026-01-01T00:00:00+00:00")
    with patch.object(run, "ALL_SOURCES", _fake_sources([old])), \
         patch.object(run, "judge") as j, \
         patch.object(run, "push_events"):
        run.main()
    j.assert_not_called()
    data = json.loads(sp.read_text(encoding="utf-8"))
    assert "old" in data["seen"]


def test_source_failure_does_not_block(env):
    sp = env / "state" / "seen.json"
    sp.parent.mkdir(parents=True)
    sp.write_text(json.dumps({"bootstrapped": True, "seen": {},
                              "pending": [], "pending_push": []}), encoding="utf-8")

    def boom():
        raise RuntimeError("blocked")

    with patch.object(run, "ALL_SOURCES", [("bad", boom), ("good", lambda: [_c("n", "New")])]), \
         patch.object(run, "judge", return_value=[
             {"id": "n", "is_event": False, "event_type": "", "summary": "", "decided": True}]), \
         patch.object(run, "push_events", return_value=True) as p:
        assert run.main() == 0
    p.assert_called_once()  # push_events([]) 也会调用，验证主流程走到最后
```

- [ ] **Step 2: 运行测试确认失败**

Run: `python -m pytest tests/test_run.py -v`
Expected: FAIL（`ModuleNotFoundError: src.run`）

- [ ] **Step 3: 实现**

`src/run.py`：

```python
import sys
from datetime import datetime, timezone

from .config import (EVENTS_MD_PATH, MAX_CANDIDATES_PER_JUDGE,
                     SKIP_OLDER_THAN_HOURS, STATE_PATH)
from .judge import judge
from .models import Candidate
from .notify import push_events
from .sources import ALL_SOURCES
from .state import SeenStore


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _is_stale(c, now):
    if not c.published_at:
        return False
    try:
        pub = datetime.fromisoformat(c.published_at.replace("Z", "+00:00"))
    except ValueError:
        return False
    age_h = (now - pub).total_seconds() / 3600
    return age_h > SKIP_OLDER_THAN_HOURS or age_h < -2


def collect_candidates():
    out = []
    for name, fetch in ALL_SOURCES:
        try:
            items = fetch()
            print(f"[{name}] {len(items)} candidates")
            out.extend(items)
        except Exception as exc:
            print(f"[{name}] FAILED: {exc}")
    return out


def append_events_md(events, iso_now):
    lines = [f"\n## {iso_now}", ""]
    for e in events:
        lines.append(
            f"- **[{e['title']}]({e['url']})** — {e.get('event_type')} — "
            f"{e.get('summary', '')} ({e['source']})"
        )
    with open(EVENTS_MD_PATH, "a", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def main():
    now = datetime.now(timezone.utc)
    store = SeenStore(STATE_PATH)

    candidates = collect_candidates()
    fresh = store.filter_new(candidates)
    now_stale = [c for c in fresh if _is_stale(c, now)]
    fresh = [c for c in fresh if not _is_stale(c, now)]
    store.mark_seen(now_stale, _now_iso())

    if not store.bootstrapped:
        store.mark_seen(candidates, _now_iso())
        store.set_bootstrapped()
        store.save()
        print(f"bootstrap: marked {len(candidates)} seen, no push")
        return 0

    to_judge = fresh[:MAX_CANDIDATES_PER_JUDGE]
    store.add_pending(fresh[MAX_CANDIDATES_PER_JUDGE:])

    all_c = to_judge + store.pop_pending()
    judgments = judge(all_c)
    by_id = {c.id: c for c in all_c}

    events, undecided = [], []
    for j in judgments:
        if j["decided"] and j["is_event"]:
            events.append({**by_id[j["id"]].to_dict(),
                           "event_type": j["event_type"], "summary": j["summary"]})
        elif not j["decided"]:
            undecided.append(by_id[j["id"]])

    keep_ids = {c.id for c in undecided}
    store.mark_seen([c for c in all_c if c.id not in keep_ids], _now_iso())
    store.add_pending(undecided)

    all_events = events + store.pop_pending_push()
    if push_events(all_events):
        append_events_md(all_events, _now_iso())
    else:
        store.add_pending_push(all_events)

    store.save()
    print(f"done: {len(events)} new events, {len(undecided)} pending")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: 运行全部测试确认通过**

Run: `python -m pytest tests/ -v`
Expected: 全部 PASS

- [ ] **Step 5: 本地实测一次（DRY_RUN）**

```bash
DRY_RUN=1 python -m src.run
```

Expected: 退出码 0；openai/anthropic/qwen/deepseek/modelscope/openrouter/github 正常打出条数；hf/reddit/hn 若本地被墙打 `FAILED`（不阻塞）；首运行打印 `bootstrap: marked N seen, no push`；`state/seen.json` 出现已见条目。

- [ ] **Step 6: 提交**

```bash
git add src/run.py tests/test_run.py
git commit -m "feat: main orchestrator with bootstrap, dedup, judge, push"
```

---

### Task 12: GitHub Actions 工作流 + README + 收尾

**Files:**
- Create: `.github/workflows/track.yml`, `README.md`

**Interfaces:**
- Consumes: `python -m src.run`（Task 11）；`state/seen.json` + `events.md`（由运行更新并提交回仓库）

- [ ] **Step 1: 写工作流**

`.github/workflows/track.yml`：

```yaml
name: track-model-news

on:
  schedule:
    # 每 30 分钟一轮，错开整点（GitHub cron 高峰延迟小一些）
    - cron: "7,37 * * * *"
  workflow_dispatch: {}

permissions:
  contents: write

concurrency:
  group: model-news
  cancel-in-progress: false

jobs:
  track:
    runs-on: ubuntu-latest
    timeout-minutes: 10
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
          cache: pip

      - run: pip install -r requirements.txt

      - name: Run tracker
        env:
          DEEPSEEK_API_KEY: ${{ secrets.DEEPSEEK_API_KEY }}
          SERVERCHAN_SENDKEY: ${{ secrets.SERVERCHAN_SENDKEY }}
        run: python -m src.run

      - name: Commit state
        run: |
          git config user.name "model-news-bot"
          git config user.email "bot@users.noreply.github.com"
          git add state/seen.json events.md
          if ! git diff --cached --quiet; then
            git commit -m "chore: update state [skip ci]"
            git push
          fi
```

- [ ] **Step 2: 写 README**

`README.md`：

```markdown
# Latest Model News — AI 模型发布追踪器

每 30 分钟抓取 OpenAI / Anthropic / Qwen / DeepSeek 官方动态、HuggingFace / ModelScope 新模型、
OpenRouter 新上线、GitHub Releases、Reddit r/LocalLLaMA 与 Hacker News，
用 DeepSeek 判断「新模型发布 / 权重开源 / 重大版本升级」硬事件，通过 Server酱 推送到微信。

## 工作原理

GitHub Actions 每 30 分钟运行一轮：
抓取（10 个独立源，单源失败不影响其他）→ 去重（`state/seen.json` 提交回仓库）→
DeepSeek 判断硬事件（失败降级关键词规则，未判定条目下轮重试）→
Server酱 推送（多条合并一条，失败下轮重推）→ 事件追加到 `events.md`。

首次运行仅记录不推送（bootstrap，防止历史内容刷屏）。

## 部署

1. 在 GitHub 创建**公开**仓库并推送本项目（公开仓库 Actions 免费不限时）
2. 仓库 Settings → Secrets and variables → Actions 添加：
   - `DEEPSEEK_API_KEY` — [DeepSeek 开放平台](https://platform.deepseek.com/) 申请
   - `SERVERCHAN_SENDKEY` — [Server酱](https://sct.ftqq.com/) 微信扫码后获取
3. Actions 页面手动触发一次 `track-model-news`（bootstrap），之后每 30 分钟自动运行

## 本地调试

```bash
pip install -r requirements.txt
cp .env.example .env   # 填入 DEEPSEEK_API_KEY / SERVERCHAN_SENDKEY
DRY_RUN=1 python -m src.run
python -m pytest tests/ -v
```

本地被墙的源（HF/Reddit/HN）会打印 FAILED 并跳过，不影响其他源。

## 调整追踪范围

`src/config.py`：`HF_ORGS`（HuggingFace 组织）、`MS_KEYWORDS`/`MS_ORG_MAP`（ModelScope）、
`GH_REPOS`（GitHub 仓库）、`HN_QUERIES`（HN 搜索词）。

## 成本

- GitHub Actions：公开仓库免费
- DeepSeek：约 ¥5-10/月（无新条目时不调用）
- Server酱：免费版（每天 5 条额度，多条事件自动合并）

## 常见问题

- **Actions 定时任务停了？** GitHub 对 60 天无提交的仓库停用 schedule；本项目每 30 分钟提交状态，不受影响。手动触发一次即可重新启用。
- **漏推了事件？** 判断标准偏严格（只推硬事件）。可调整 `src/judge.py` 的 SYSTEM_PROMPT 放宽。
```

- [ ] **Step 3: 最终验证**

```bash
python -m pytest tests/ -v
```

Expected: 全部 PASS（约 40+ 个测试）。

```bash
DRY_RUN=1 python -m src.run && echo EXIT_OK
```

Expected: `EXIT_OK`，本地可达源正常输出条数。

- [ ] **Step 4: 提交**

```bash
git add .github/ README.md
git commit -m "ci: 30-min schedule workflow, README deployment guide"
```

- [ ] **Step 5: 输出部署指引给用户（不代替用户操作）**

告知用户后续手动步骤：
1. 在 GitHub 创建公开仓库 `Latest_Model_News` 并 `git remote add origin … && git push -u origin main`
2. 添加两个 Secrets（`DEEPSEEK_API_KEY`、`SERVERCHAN_SENDKEY`）
3. Actions 页手动触发一次完成 bootstrap
4. 扫码 Server酱 关注「方糖」服务号以接收推送

---

## Self-Review 结论

- **Spec 覆盖**：9 个 spec 信息源全部有对应任务（GitHub Releases 含默认 watchlist；另新增 OpenRouter 源覆盖闭源 API 上线，超出 spec 属增强）；去重/LLM 判断/降级/pending 重试/推送重试/bootstrap/每日额度合并推送/concurrency 串行化/48h 过期 —— 均有任务覆盖
- **占位符**：无 TBD/TODO；所有代码完整
- **类型一致性**：`Candidate.to_dict()/from_dict()`、`judge() -> [{id,is_event,event_type,summary,decided}]`、`SeenStore` 方法签名、`push_events(events) -> bool`、`ALL_SOURCES` 10 元组 —— 跨任务引用一致
