import re

from ..config import ANTHROPIC_NEWS_URL
from ..http_client import get_text
from ..models import Candidate

_SLUG_RE = re.compile(r'href="/news/([a-z0-9-]{6,80})"')
_DATE_RE = re.compile(r"([A-Z][a-z]{2}) (\d{1,2}), (\d{4})")
_TITLE_RE = re.compile(r">([^<>]{20,120})</h4>")
_MONTHS = {m: i + 1 for i, m in enumerate(
    ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"])}


def _to_iso(s):
    m = _DATE_RE.match(s)
    if not m:
        return None
    month, day, year = m.groups()
    return f"{year}-{_MONTHS[month]:02d}-{int(day):02d}T00:00:00+00:00"


def fetch():
    html = get_text(ANTHROPIC_NEWS_URL)
    seen, out = set(), []
    for m in _SLUG_RE.finditer(html):
        slug = m.group(1)
        if slug in seen:
            continue
        seen.add(slug)
        window = html[m.end():m.end() + 600]
        dm = _DATE_RE.search(window)
        tm = _TITLE_RE.search(window)
        out.append(Candidate(
            id=f"anthropic:{slug}",
            source="anthropic",
            title=tm.group(1).strip() if tm else slug.replace("-", " ").title(),
            url=f"https://www.anthropic.com/news/{slug}",
            published_at=_to_iso(dm.group(0)) if dm else None,
        ))
    return out
