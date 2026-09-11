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
