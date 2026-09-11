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
