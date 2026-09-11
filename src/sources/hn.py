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
